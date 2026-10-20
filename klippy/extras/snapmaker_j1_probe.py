# Snapmaker J1 nozzle contact probe (one sensor per IDEX carriage)
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
from . import probe

# Each J1 toolhead detects a nozzle contact with its own switch.  The
# probe uses the switch of the currently active carriage, so the
# regular probe tools (PROBE, PROBE_ACCURACY, screws_tilt_adjust,
# bed_mesh, ...) work with either nozzle.  The nozzle can also probe
# horizontally; this is used to measure the XY offset between both
# nozzles against the calibration feature in the bed center.
#
# The calibration commands (SNAPMAKER_CAL_*) implement the steps of the
# stock calibration workflows.  They measure on the bare heated bed
# (build plate removed) and collect their results in a session; nothing
# is stored until SNAPMAKER_CAL_FINISH SAVE=1.

HEIGHT_VALID_RANGE = 0.08
LIVE_RETRACT = 2.

class NozzleSwitch:
    def __init__(self, config, pin_name, probe_offsets, param_helper):
        self.printer = config.get_printer()
        ppins = self.printer.lookup_object('pins')
        self.mcu_endstop = ppins.setup_pin('endstop', config.get(pin_name))
        self.homing_helper = probe.DescendToEndstopHelper(
            config, self.mcu_endstop, probe_offsets, param_helper)
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
    def _handle_mcu_identify(self):
        # Horizontal probing stops the x and y steppers via this switch
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis('x') or stepper.is_active_axis('y'):
                self.mcu_endstop.add_stepper(stepper)

class SnapmakerJ1Probe:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.probe_offsets = probe.ProbeOffsetsHelper(config)
        self.param_helper = probe.ProbeParameterHelper(config)
        self.switches = [
            NozzleSwitch(config, 'pin_t0', self.probe_offsets,
                         self.param_helper),
            NozzleSwitch(config, 'pin_t1', self.probe_offsets,
                         self.param_helper)]
        # Sensor power
        self.power_pin = None
        self.power_delay = config.getfloat('power_on_delay', .100, minval=0.)
        power_pin = config.get('power_pin', None)
        if power_pin is not None:
            ppins = self.printer.lookup_object('pins')
            self.power_pin = ppins.setup_pin('digital_out', power_pin)
            self.power_pin.setup_max_duration(0.)
            self.power_pin.setup_start_value(0., 0.)
        self.power_state = False
        # Calibration points (index 0 is the XY calibration feature)
        points = config.getlists('calibration_points', seps=(',', '\n'),
                                 parser=float, count=2)
        self.points = [tuple(p) for p in points]
        self.travel_z = config.getfloat('travel_z', 15.)
        self.travel_speed = config.getfloat('travel_speed', 150., above=0.)
        # Horizontal probing parameters
        self.xy_probe_z = config.getfloat('xy_probe_z')
        self.xy_distance = config.getfloat('xy_probe_distance', 15., above=0.)
        self.xy_speed = config.getfloat('xy_probe_speed', 13.3, above=0.)
        self.xy_slow_speed = config.getfloat('xy_probe_slow_speed', 1.3,
                                             above=0.)
        self.xy_retract = config.getfloat('xy_retract_dist', 1., above=0.)
        self.xy_samples = config.getint('xy_samples', 5, minval=3)
        self.xy_tolerance = config.getfloat('xy_tolerance', 0.25, above=0.)
        self.max_t1_offset = config.getfloat('max_t1_offset', 5., above=0.)
        self.max_center_offset = config.getfloat('max_center_offset', 5.,
                                                 above=0.)
        # Probe session handling
        self.active = None
        self.probe_session = probe.SampleAveragingHelper(
            config, self.param_helper, self._start_session)
        self.cmd_helper = probe.ProbeCommandHelper(config, self,
                                                   self._query_endstop)
        self.printer.add_object('probe', self)
        # Calibration session
        self._reset_calibration()
        gcode = self.printer.lookup_object('gcode')
        for cmd in ['PROBE_XY_CENTER', 'Z_ENDSTOP_ADJUST', 'CAL_START',
                    'CAL_MOVE', 'CAL_DATUM', 'CAL_HEIGHT', 'CAL_SET_ORIGIN',
                    'CAL_XY', 'CAL_NOZZLE_OFFSET', 'CAL_FINISH']:
            func = getattr(self, 'cmd_SNAPMAKER_' + cmd)
            gcode.register_command('SNAPMAKER_' + cmd, func,
                                   desc=getattr(self, 'cmd_SNAPMAKER_'
                                                + cmd + '_help'))
    # Probe interface
    def get_probe_params(self, gcmd=None):
        return self.param_helper.get_probe_params(gcmd)
    def get_offsets(self, gcmd=None):
        return self.probe_offsets.get_offsets(gcmd)
    def get_status(self, eventtime):
        status = self.cmd_helper.get_status(eventtime)
        diff = self.height_difference
        status['calibration'] = {
            'active': self.cal_active,
            'datum': self.datum,
            'height_difference': diff,
            'height_valid': (diff is not None
                             and abs(diff) < .5 * HEIGHT_VALID_RANGE),
            'z_origin_offset': self.pending_z,
            't1_offset': self.pending_t1,
            'bed_center_offset': self.pending_center}
        return status
    def start_probe_session(self, gcmd):
        return self.probe_session.start_probe_session(gcmd)
    # Sensor and carriage selection
    def _carriage_modes(self):
        dc = self.printer.lookup_object('dual_carriage', None)
        if dc is None:
            return ['PRIMARY', 'INACTIVE']
        status = dc.get_status()
        return [status.get('carriage_0'), status.get('carriage_1')]
    def _active_index(self):
        modes = self._carriage_modes()
        if 'COPY' in modes or 'MIRROR' in modes:
            raise self.printer.command_error(
                "Probing requires a single active carriage")
        return 1 if modes[1] == 'PRIMARY' else 0
    def _switch(self):
        return self.switches[self._active_index()]
    def _dc_rails(self):
        return list(self.printer.lookup_object('dual_carriage')
                    .dc_rails.values())
    def _activate_carriage(self, index):
        gcode = self.printer.lookup_object('gcode')
        gcode.run_script_from_command("SET_DUAL_CARRIAGE CARRIAGE=%d"
                                      % (index,))
    def _select_carriage(self, index):
        # Make sure the other carriage waits at its endstop (as the stock
        # firmware does before every measurement), so the active nozzle
        # can reach every calibration point
        toolhead = self.printer.lookup_object('toolhead')
        rails = self._dc_rails()
        other = rails[1 - index]
        park_x = other.rail.get_homing_info().position_endstop
        dc = self.printer.lookup_object('dual_carriage')
        positions = dc.save_dual_carriage_state()['carriage_positions']
        if abs(positions[other.get_name()] - park_x) > .01:
            if self._active_index() != 1 - index:
                self._activate_carriage(1 - index)
            toolhead.manual_move([park_x], self.travel_speed)
        if self._active_index() != index:
            self._activate_carriage(index)
    def _query_endstop(self, print_time):
        return self._switch().mcu_endstop.query_endstop(print_time)
    def _set_power(self, state):
        if self.power_pin is None or state == self.power_state:
            return
        self.power_state = state
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.register_lookahead_callback(
            lambda print_time: self.power_pin.set_digital(print_time, state))
        if state:
            toolhead.dwell(self.power_delay)
    def _start_session(self, gcmd):
        self._set_power(True)
        self.active = self._switch()
        self.active.homing_helper.clear_trigger_positions()
        return self
    # Hardware probe session interface used by SampleAveragingHelper
    def run_probe(self, gcmd):
        self.active.homing_helper.descend_until_trigger(gcmd)
    def pull_probed_results(self):
        return self.active.homing_helper.pull_trigger_positions()
    def end_probe_session(self):
        self.active.homing_helper.clear_trigger_positions()
        self.active = None
        if not self.cal_active:
            self._set_power(False)
    # Helpers
    def _check_homed(self):
        toolhead = self.printer.lookup_object('toolhead')
        curtime = self.printer.get_reactor().monotonic()
        homed = toolhead.get_status(curtime)['homed_axes']
        if 'x' not in homed or 'y' not in homed or 'z' not in homed:
            raise self.printer.command_error("Must home before probing")
    def _center_offset(self):
        # Correction of the calibration points measured by the XY
        # calibration (ignored if implausible, as the stock firmware does)
        svv = self.printer.lookup_object('save_variables', None)
        offset = [0., 0.]
        if svv is not None:
            offset = svv.allVariables.get('snap_j1_bed_center_offset', offset)
        if max(abs(offset[0]), abs(offset[1])) > self.max_center_offset:
            return [0., 0.]
        return offset
    def _point(self, gcmd):
        index = gcmd.get_int('POINT', minval=0, maxval=len(self.points) - 1)
        offset = self._center_offset()
        return (self.points[index][0] + offset[0],
                self.points[index][1] + offset[1])
    def _move_to(self, xy, tool, z=None, keep_z=False):
        toolhead = self.printer.lookup_object('toolhead')
        cur_z = toolhead.get_position()[2]
        if keep_z:
            z = cur_z
            travel_z = cur_z + LIVE_RETRACT
        else:
            travel_z = max(cur_z, self.travel_z)
        lift_speed = self.get_probe_params()['lift_speed']
        toolhead.manual_move([None, None, travel_z], lift_speed)
        self._select_carriage(tool)
        toolhead.manual_move(list(xy), self.travel_speed)
        if z is not None:
            toolhead.manual_move([None, None, z], lift_speed)
    def _probe_z(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        try:
            pos = probe.run_single_probe(self, gcmd)
        except self.printer.command_error:
            # The bed may have been raised into the nozzle meanwhile
            if not self._query_endstop(toolhead.get_last_move_time()):
                raise
            toolhead.manual_move([None, None, toolhead.get_position()[2]
                                  + LIVE_RETRACT],
                                 self.get_probe_params(gcmd)['lift_speed'])
            pos = probe.run_single_probe(self, gcmd)
        toolhead.manual_move([None, None, pos.bed_z + LIVE_RETRACT],
                             self.get_probe_params(gcmd)['lift_speed'])
        return pos.bed_z
    # Horizontal probing
    def _probe_axis(self, axis, direction):
        # Approach once quickly, then take slow samples and drop the
        # extremes (the same sequence as the stock firmware)
        toolhead = self.printer.lookup_object('toolhead')
        phoming = self.printer.lookup_object('homing')
        mcu_endstop = self._switch().mcu_endstop
        start = toolhead.get_position()
        speed = self.xy_speed
        distance = self.xy_distance
        samples = []
        while len(samples) < self.xy_samples:
            target = list(start)
            target[axis] += direction * distance
            epos = phoming.probing_move(mcu_endstop, target, speed)
            if speed != self.xy_speed:
                samples.append(epos[axis])
            start = list(epos)
            start[axis] -= direction * self.xy_retract
            toolhead.manual_move(start, self.xy_speed)
            speed = self.xy_slow_speed
            distance = self.xy_retract + 2. * self.xy_tolerance
        if max(samples) - min(samples) > self.xy_tolerance:
            raise self.printer.command_error(
                "XY probe samples exceed tolerance (%.3f)"
                % (max(samples) - min(samples),))
        samples.sort()
        trimmed = samples[1:-1]
        return sum(trimmed) / len(trimmed)
    def _probe_xy_center(self, gcmd, tool):
        self._check_homed()
        toolhead = self.printer.lookup_object('toolhead')
        lift_speed = self.get_probe_params(gcmd)['lift_speed']
        cx, cy = self.points[0]
        probe_z = gcmd.get_float('Z', self.xy_probe_z, maxval=0.)
        self._move_to((cx, cy), tool)
        self._set_power(True)
        try:
            # Descend with the switch armed so a forgotten build plate
            # stops the nozzle instead of crashing into it
            phoming = self.printer.lookup_object('homing')
            target = toolhead.get_position()
            target[2] = probe_z
            endstops = [(self._switch().mcu_endstop, "probe")]
            epos = phoming.manual_home(toolhead, endstops, target, lift_speed,
                                       probe_pos=True, triggered=True,
                                       check_triggered=False)
            if epos[2] > probe_z + 0.01:
                toolhead.manual_move([None, None, self.travel_z], lift_speed)
                raise gcmd.error("Nozzle contact at Z=%.3f before reaching"
                                 " the calibration height - remove the"
                                 " build plate" % (epos[2],))
            center = []
            for axis in (0, 1):
                low = self._probe_axis(axis, -1.)
                toolhead.manual_move([cx, cy], self.xy_speed)
                high = self._probe_axis(axis, 1.)
                toolhead.manual_move([cx, cy], self.xy_speed)
                center.append(.5 * (low + high))
            toolhead.manual_move([None, None, self.travel_z], lift_speed)
        finally:
            if not self.cal_active:
                self._set_power(False)
        gcmd.respond_info("T%d: calibration center at X=%.4f Y=%.4f"
                          % (tool, center[0], center[1]))
        return center
    cmd_SNAPMAKER_PROBE_XY_CENTER_help = (
        "Measure the bed calibration center with a nozzle (TOOL=)")
    def cmd_SNAPMAKER_PROBE_XY_CENTER(self, gcmd):
        self._probe_xy_center(gcmd, gcmd.get_int('TOOL', 0, minval=0,
                                                  maxval=1))
    # Z origin
    def _z_rail(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        return [r for r in kin.rails if r.get_name() == 'stepper_z'][0]
    def _store_z_origin(self, gcmd, offset):
        # The bed homes to the Z maximum, so its endstop position doubles
        # as the travel limit and both must move together
        endstop = self._z_rail().get_homing_info().position_endstop - offset
        gcmd.respond_info(
            "stepper_z: position_endstop: %.3f\n"
            "The SAVE_CONFIG command will update the printer config file\n"
            "and restart the printer." % (endstop,))
        configfile = self.printer.lookup_object('configfile')
        configfile.set('stepper_z', 'position_endstop', "%.3f" % (endstop,))
        configfile.set('stepper_z', 'position_max', "%.3f" % (endstop,))
    cmd_SNAPMAKER_Z_ENDSTOP_ADJUST_help = (
        "Move the Z origin up by OFFSET (stores the Z endstop position)")
    def cmd_SNAPMAKER_Z_ENDSTOP_ADJUST(self, gcmd):
        self._store_z_origin(gcmd, gcmd.get_float('OFFSET'))
    # Calibration session
    def _reset_calibration(self):
        self.cal_active = False
        self.datum = self.height_difference = None
        self.pending_z = self.pending_t1 = self.pending_center = None
        self.plate_thickness = 0.
    def _check_session(self):
        if not self.cal_active:
            raise self.printer.command_error(
                "No calibration active (SNAPMAKER_CAL_START)")
    cmd_SNAPMAKER_CAL_START_help = (
        "Start a calibration session (THICKNESS= build plate thickness)")
    def cmd_SNAPMAKER_CAL_START(self, gcmd):
        modes = self._carriage_modes()
        if 'COPY' in modes or 'MIRROR' in modes:
            raise gcmd.error("Calibration requires full control mode")
        self._reset_calibration()
        self.plate_thickness = gcmd.get_float('THICKNESS', 5., minval=0.)
        self.cal_active = True
    cmd_SNAPMAKER_CAL_MOVE_help = (
        "Move a nozzle above a calibration point (POINT= TOOL= Z= KEEP_Z=)")
    def cmd_SNAPMAKER_CAL_MOVE(self, gcmd):
        self._check_session()
        self._check_homed()
        self._move_to(self._point(gcmd),
                      gcmd.get_int('TOOL', 0, minval=0, maxval=1),
                      gcmd.get_float('Z', None),
                      gcmd.get_int('KEEP_Z', 0))
    cmd_SNAPMAKER_CAL_DATUM_help = (
        "Probe the bare bed with the left nozzle as height reference (POINT=)")
    def cmd_SNAPMAKER_CAL_DATUM(self, gcmd):
        # The stock firmware also derives the Z origin from this reference:
        # the print surface is the bed surface plus the plate thickness
        self._check_session()
        self._check_homed()
        self._set_power(True)
        self._move_to(self._point(gcmd), 0)
        self.datum = self._probe_z(gcmd)
        self.height_difference = None
        self.pending_z = self.datum + self.plate_thickness
        gcmd.respond_info("Bed reference at Z=%.3f" % (self.datum,))
    cmd_SNAPMAKER_CAL_HEIGHT_help = (
        "Probe a point relative to the reference (POINT= TOOL=)")
    def cmd_SNAPMAKER_CAL_HEIGHT(self, gcmd):
        # Repeated calls at the same point give a live reading while the
        # user turns a leveling wheel
        self._check_session()
        if self.datum is None:
            raise gcmd.error("No reference measured (SNAPMAKER_CAL_DATUM)")
        self._set_power(True)
        xy = self._point(gcmd)
        tool = gcmd.get_int('TOOL', 0, minval=0, maxval=1)
        toolhead = self.printer.lookup_object('toolhead')
        pos = toolhead.get_position()
        at_point = (self._active_index() == tool
                    and abs(pos[0] - xy[0]) < .01 and abs(pos[1] - xy[1]) < .01)
        if not at_point:
            self._move_to(xy, tool)
        self.height_difference = self._probe_z(gcmd) - self.datum
        gcmd.respond_info("Height difference %.3f" % (self.height_difference,))
    cmd_SNAPMAKER_CAL_SET_ORIGIN_help = (
        "Use the current nozzle height as Z origin (manual calibration)")
    def cmd_SNAPMAKER_CAL_SET_ORIGIN(self, gcmd):
        self._check_session()
        toolhead = self.printer.lookup_object('toolhead')
        self.pending_z = toolhead.get_position()[2]
        gcmd.respond_info("New Z origin at current Z=%.3f" % (self.pending_z,))
    cmd_SNAPMAKER_CAL_XY_help = (
        "Measure the XY offset of the right nozzle (build plate removed)")
    def cmd_SNAPMAKER_CAL_XY(self, gcmd):
        self._check_session()
        if self.pending_z is None and gcmd.get_int('REQUIRE_Z', 0):
            raise gcmd.error("Calibrate the Z offset first")
        probe_z = -1.2 - self.plate_thickness
        gcmd = self.printer.lookup_object('gcode').create_gcode_command(
            gcmd.get_command(), gcmd.get_commandline(),
            dict(gcmd.get_command_parameters(), Z=str(probe_z)))
        center0 = self._probe_xy_center(gcmd, 0)
        try:
            center1 = self._probe_xy_center(gcmd, 1)
        finally:
            self._select_carriage(0)
        dx = center1[0] - center0[0]
        dy = center1[1] - center0[1]
        if abs(dx) > self.max_t1_offset or abs(dy) > self.max_t1_offset:
            raise gcmd.error("T1 offset (%.3f, %.3f) exceeds max_t1_offset"
                             % (dx, dy))
        # T1's X frame is corrected through its endstop position; the
        # tool change macros apply the Y offset as a gcode offset, so T1
        # is commanded dy further to reach the same point as T0
        rail = self._dc_rails()[1].rail
        self.pending_t1 = [rail.get_homing_info().position_endstop - dx, dy]
        self.pending_center = [center0[0] - self.points[0][0],
                               center0[1] - self.points[0][1]]
        gcmd.respond_info("T1 offset relative to T0: X=%.4f Y=%.4f" % (dx, dy))
    cmd_SNAPMAKER_CAL_NOZZLE_OFFSET_help = (
        "Correct the right nozzle offset from a test print"
        " (X_ADJUST= Y_ADJUST= shift of T1 relative to T0)")
    def cmd_SNAPMAKER_CAL_NOZZLE_OFFSET(self, gcmd):
        self._check_session()
        if self.pending_t1 is None:
            svv = self.printer.lookup_object('save_variables')
            self.pending_t1 = [
                self._dc_rails()[1].rail.get_homing_info().position_endstop,
                svv.allVariables.get('snap_j1_t1_offset_y', 0.)]
        self.pending_t1[0] -= gcmd.get_float('X_ADJUST', 0.)
        self.pending_t1[1] -= gcmd.get_float('Y_ADJUST', 0.)
    cmd_SNAPMAKER_CAL_FINISH_help = (
        "End the calibration session, storing its results if SAVE=1")
    def cmd_SNAPMAKER_CAL_FINISH(self, gcmd):
        save = gcmd.get_int('SAVE', 0)
        if save and self.cal_active:
            gcode = self.printer.lookup_object('gcode')
            configfile = self.printer.lookup_object('configfile')
            if self.pending_z is not None:
                self._store_z_origin(gcmd, self.pending_z)
            if self.pending_t1 is not None:
                endstop, offset_y = self.pending_t1
                configfile.set('dual_carriage', 'position_endstop',
                               "%.4f" % (endstop,))
                configfile.set('dual_carriage', 'position_max',
                               "%.4f" % (endstop,))
                gcode.run_script_from_command(
                    "SAVE_VARIABLE VARIABLE=snap_j1_t1_offset_y VALUE=%.4f\n"
                    "SET_GCODE_VARIABLE MACRO=_SNAPMAKER_STATE"
                    " VARIABLE=t1_offset_y VALUE=%.4f"
                    % (offset_y, offset_y))
            if self.pending_center is not None:
                gcode.run_script_from_command(
                    "SAVE_VARIABLE VARIABLE=snap_j1_bed_center_offset"
                    " VALUE=[%.4f,%.4f]" % tuple(self.pending_center))
        self._reset_calibration()
        self._set_power(False)

def load_config(config):
    return SnapmakerJ1Probe(config)
