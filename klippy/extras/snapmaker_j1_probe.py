# Snapmaker J1 nozzle contact probe (one sensor per IDEX carriage)
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import collections, logging, math
import mcu
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
#
# Calibration touches follow the stock firmware (calibtration.cpp): the
# nozzle approaches until its switch closes and then moves back until
# the switch opens again; the opening point is the measurement.  A
# measurement starts with a fast touch, guarded by the StallGuard
# output of the moving driver, followed by slow touches whose highest
# and lowest results are dropped.

HEIGHT_VALID_RANGE = 0.08
LIVE_RETRACT = 2.
# Trigger reason of a driver DIAG line (the reasons of klippy/mcu.py
# end at REASON_COMMS_TIMEOUT)
REASON_STALLGUARD = 8

# Stock StallGuard thresholds (probe_sg_reg) and the conversion of a
# measured SG_RESULT into a threshold (J1.cpp): divisor, offset and the
# minimum speed of the driver's axis for a measurement
SG_DEFAULTS = collections.OrderedDict([
    ('stepper_x', 20), ('dual_carriage', 20), ('stepper_y', 20),
    ('stepper_z', 80)])
SG_MEASURE = {'stepper_x': (12., 0., 50.), 'dual_carriage': (12., 0., 50.),
              'stepper_y': (10., 0., 50.), 'stepper_z': (3., -25., 3.)}
SG_MIN_CRUISE_TIME = 0.300
SG_MIN_SAMPLES = 3

# Endstop of a nozzle switch.  The DIAG (StallGuard) line of a driver
# can be armed to stop the same move; the move then fails with a stall
# error instead of reporting a contact.
class NozzleEndstop:
    def __init__(self, printer, pin_desc):
        self._printer = printer
        ppins = printer.lookup_object('pins')
        pin_params = ppins.lookup_pin(pin_desc, can_invert=True,
                                      can_pullup=True)
        self._mcu = pin_params['chip']
        self._pin = pin_params['pin']
        self._pullup = pin_params['pullup']
        self._invert = pin_params['invert']
        self._oid = self._mcu.create_oid()
        self._home_cmd = self._query_cmd = None
        self._rest_ticks = 0
        self._dispatch = mcu.TriggerDispatch(self._mcu)
        self._mcu.register_config_callback(self._build_config)
        self.guards = []
        self._homing_guards = []
        self.stalled = False
    def get_mcu(self):
        return self._mcu
    def add_stepper(self, stepper):
        self._dispatch.add_stepper(stepper)
    def get_steppers(self):
        return self._dispatch.get_steppers()
    def _build_config(self):
        self._mcu.add_config_cmd("config_endstop oid=%d pin=%s pull_up=%d"
                                 % (self._oid, self._pin, self._pullup))
        self._mcu.add_config_cmd(
            "endstop_home oid=%d clock=0 sample_ticks=0 sample_count=0"
            " rest_ticks=0 pin_value=0 trsync_oid=0 trigger_reason=0"
            % (self._oid,), on_restart=True)
        # The DIAG lines are armed through the same command queue, so
        # they always start after the trsync of this endstop
        cmd_queue = self._dispatch.get_command_queue()
        self._home_cmd = self._mcu.lookup_command(
            "endstop_home oid=%c clock=%u sample_ticks=%u sample_count=%c"
            " rest_ticks=%u pin_value=%c trsync_oid=%c trigger_reason=%c",
            cq=cmd_queue)
        self._query_cmd = self._mcu.lookup_query_command(
            "endstop_query_state oid=%c",
            "endstop_state oid=%c homing=%c next_clock=%u pin_value=%c",
            oid=self._oid, cq=cmd_queue)
    def home_start(self, print_time, sample_time, sample_count, rest_time,
                   triggered=True):
        clock = self._mcu.print_time_to_clock(print_time)
        rest_ticks = self._mcu.print_time_to_clock(print_time+rest_time) - clock
        self._rest_ticks = rest_ticks
        sample_ticks = self._mcu.seconds_to_clock(sample_time)
        trigger_completion = self._dispatch.start(print_time)
        trsync_oid = self._dispatch.get_oid()
        self._home_cmd.send(
            [self._oid, clock, sample_ticks, sample_count, rest_ticks,
             triggered ^ self._invert, trsync_oid,
             mcu.MCU_trsync.REASON_ENDSTOP_HIT], reqclock=clock)
        self._homing_guards = list(self.guards)
        for guard in self._homing_guards:
            self._home_cmd.send(
                [guard.oid, clock, sample_ticks, sample_count, rest_ticks,
                 1 ^ guard.invert, trsync_oid, REASON_STALLGUARD],
                reqclock=clock)
        self.stalled = False
        return trigger_completion
    def home_wait(self, home_end_time):
        self._dispatch.wait_end(home_end_time)
        for oid in [self._oid] + [g.oid for g in self._homing_guards]:
            self._home_cmd.send([oid, 0, 0, 0, 0, 0, 0, 0])
        self._homing_guards = []
        res = self._dispatch.stop()
        cmderr = self._printer.command_error
        if res == REASON_STALLGUARD:
            self.stalled = True
            raise cmderr("StallGuard detected a blocked axis")
        if res >= mcu.MCU_trsync.REASON_COMMS_TIMEOUT:
            raise cmderr("Communication timeout during homing")
        if res != mcu.MCU_trsync.REASON_ENDSTOP_HIT:
            return 0.
        if self._mcu.is_fileoutput():
            return home_end_time
        params = self._query_cmd.send([self._oid])
        next_clock = self._mcu.clock32_to_clock64(params['next_clock'])
        return self._mcu.clock_to_print_time(next_clock - self._rest_ticks)
    def query_endstop(self, print_time):
        clock = self._mcu.print_time_to_clock(print_time)
        if self._mcu.is_fileoutput():
            return 0
        params = self._query_cmd.send([self._oid], minclock=clock)
        return params['pin_value'] ^ self._invert

# DIAG output of one or more drivers (revision 1 boards combine all of
# them on one line)
class DiagLine:
    def __init__(self, printer, pin_params):
        self.mcu = pin_params['chip']
        self.pin = pin_params['pin']
        self.pullup = pin_params['pullup']
        self.invert = pin_params['invert']
        self.oid = self.mcu.create_oid()
        self._query_cmd = None
        self.mcu.register_config_callback(self._build_config)
    def _build_config(self):
        self.mcu.add_config_cmd("config_endstop oid=%d pin=%s pull_up=%d"
                                % (self.oid, self.pin, self.pullup))
        self.mcu.add_config_cmd(
            "endstop_home oid=%d clock=0 sample_ticks=0 sample_count=0"
            " rest_ticks=0 pin_value=0 trsync_oid=0 trigger_reason=0"
            % (self.oid,), on_restart=True)
        self._query_cmd = self.mcu.lookup_query_command(
            "endstop_query_state oid=%c",
            "endstop_state oid=%c homing=%c next_clock=%u pin_value=%c",
            oid=self.oid)
    def is_active(self):
        if self.mcu.is_fileoutput():
            return False
        params = self._query_cmd.send([self.oid])
        return bool(params['pin_value'] ^ self.invert)

# StallGuard of the X, Y and Z drivers as the stock firmware uses it
# (motion_control.cpp): only the driver of the moving axis signals a
# stall, with a threshold derived from its load during earlier moves
class StallGuard:
    def __init__(self, config):
        self.printer = config.get_printer()
        ppins = self.printer.lookup_object('pins')
        self.lines = {}
        self.thresholds = {}
        self.fixed = set()
        self.measured = {}
        self.measure = config.getboolean('stallguard_measure', True)
        lines_by_pin = {}
        for name, default in SG_DEFAULTS.items():
            desc = config.get('stallguard_pin_' + name, None)
            if desc is None:
                continue
            params = ppins.parse_pin(desc, can_invert=True, can_pullup=True)
            key = (params['chip_name'], params['pin'])
            line = lines_by_pin.get(key)
            if line is None:
                params = ppins.lookup_pin(desc, can_invert=True,
                                          can_pullup=True)
                line = lines_by_pin[key] = DiagLine(self.printer, params)
            elif (line.invert, line.pullup) != (params['invert'],
                                                params['pullup']):
                raise config.error("StallGuard pin %s must have the same"
                                   " polarity everywhere" % (desc,))
            self.lines[name] = line
            threshold = config.getint('stallguard_threshold_' + name, None,
                                      minval=1, maxval=255)
            if threshold is None:
                threshold = default
            else:
                self.fixed.add(name)
            self.thresholds[name] = threshold
        self.tmcs = {}
        self.printer.register_event_handler('klippy:connect',
                                            self._handle_connect)
    def _handle_connect(self):
        for name in self.lines:
            tmc = self.printer.lookup_object('tmc2209 ' + name, None)
            if tmc is None:
                raise self.printer.config_error(
                    "StallGuard of %s requires a [tmc2209 %s] section"
                    % (name, name))
            self.tmcs[name] = tmc
    def has(self, name):
        return name in self.lines
    # Driver registers
    def _write_fields(self, name, values):
        tmc = self.tmcs[name]
        previous = {}
        regs = collections.OrderedDict()
        for field, value in values:
            previous[field] = tmc.fields.get_field(field)
            reg = tmc.fields.lookup_register(field)
            regs[reg] = tmc.fields.set_field(field, value)
        for reg, val in regs.items():
            tmc.mcu_tmc.set_register(reg, val)
        return previous
    def arm(self, name):
        # StallGuard4 works in StealthChop only; the DIAG output needs
        # TCOOLTHRS above the step interval (as in the stock firmware)
        return self._write_fields(name, [
            ('sgthrs', self.thresholds[name]), ('tcoolthrs', 0xfffff),
            ('tpwmthrs', 0), ('en_spreadcycle', 0)])
    def disarm(self, name, previous):
        self._write_fields(name, list(previous.items()))
    # Threshold measurement
    def _wants_measurement(self, name):
        return (self.measure and name in self.lines and name not in self.fixed
                and name not in self.measured
                and not self.tmcs[name].fields.get_field('en_spreadcycle'))
    def _measurable(self, toolhead, start, target, speed, axis_steppers):
        if self.printer.lookup_object('mcu').is_fileoutput():
            return [], 0., 1.
        axes_d = [t - s for t, s in zip(target[:3], start[:3])]
        move_d = math.sqrt(sum([d*d for d in axes_d]))
        if not move_d:
            return [], 0., 1.
        max_v, max_a = toolhead.get_max_velocity()
        kin = toolhead.get_kinematics()
        if axes_d[2] and hasattr(kin, 'max_z_velocity'):
            ratio = move_d / abs(axes_d[2])
            max_v = min(max_v, kin.max_z_velocity * ratio)
            max_a = min(max_a, kin.max_z_accel * ratio)
        velocity = min(speed, max_v)
        cruise_d = move_d - velocity * velocity / max_a
        if cruise_d / velocity < SG_MIN_CRUISE_TIME:
            return [], 0., 1.
        names = []
        for axis, name in axis_steppers:
            if not self._wants_measurement(name):
                continue
            min_speed = SG_MEASURE[name][2]
            if velocity * abs(axes_d[axis]) / move_d >= min_speed:
                names.append(name)
        return names, velocity, max_a
    def move(self, coord, speed, axis_steppers):
        # Travel move (as toolhead.manual_move) that reads SG_RESULT of
        # the moving drivers while they cruise; the stock firmware takes
        # its thresholds from the first such moves after a restart
        toolhead = self.printer.lookup_object('toolhead')
        start = toolhead.get_position()
        target = list(start)
        for i, c in enumerate(coord):
            if c is not None:
                target[i] = c
        names, velocity, accel = self._measurable(toolhead, start, target,
                                                  speed, axis_steppers)
        if not names:
            toolhead.manual_move(coord, speed)
            return
        toolhead.wait_moves()
        move_start = toolhead.get_last_move_time()
        toolhead.manual_move(coord, speed)
        move_end = toolhead.get_last_move_time()
        accel_t = velocity / accel
        cruise_start, cruise_end = move_start + accel_t, move_end - accel_t
        reactor = self.printer.get_reactor()
        main_mcu = self.printer.lookup_object('mcu')
        samples = {name: [] for name in names}
        while 1:
            eventtime = reactor.monotonic()
            print_time = main_mcu.estimated_print_time(eventtime)
            if print_time >= cruise_end:
                break
            if print_time < cruise_start:
                reactor.pause(eventtime + min(cruise_start - print_time, .050))
                continue
            for name in names:
                tmc = self.tmcs[name]
                val = tmc.mcu_tmc.get_register('SG_RESULT')
                samples[name].append(tmc.fields.get_field('sg_result', val))
        toolhead.wait_moves()
        for name, values in samples.items():
            if len(values) < SG_MIN_SAMPLES:
                continue
            values.sort()
            sg_result = values[len(values) // 2]
            divisor, offset, min_speed = SG_MEASURE[name]
            threshold = int(sg_result / divisor + offset)
            if not 1 <= threshold <= 255:
                logging.info("StallGuard %s: SG_RESULT %d gives no usable"
                             " threshold", name, sg_result)
                continue
            self.measured[name] = sg_result
            self.thresholds[name] = threshold
            logging.info("StallGuard %s: SG_RESULT %d (%d samples),"
                         " threshold %d", name, sg_result, len(values),
                         threshold)
    def get_status(self):
        return {name: {'threshold': self.thresholds[name],
                       'sg_result': self.measured.get(name)}
                for name in self.lines}

class NozzleSwitch:
    def __init__(self, config, pin_name, probe_offsets, param_helper):
        self.printer = config.get_printer()
        self.mcu_endstop = NozzleEndstop(self.printer, config.get(pin_name))
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
        self.stallguard = StallGuard(config)
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
        # Calibration touches (stock: 300 mm/min fast, a tenth of it for
        # the samples and a quarter for the live height measurement)
        self.backoff = config.getfloat('probe_backoff', 1., above=0.)
        self.max_delta = config.getfloat('probe_max_delta', .25, above=0.)
        self.cal_samples = config.getint('probe_samples', 5, minval=3)
        self.z_distance = config.getfloat('z_probe_distance', 30., above=0.)
        self.z_speed = config.getfloat('z_probe_speed', 5., above=0.)
        self.z_slow_speed = config.getfloat('z_probe_slow_speed', .5,
                                            above=0.)
        self.z_live_speed = config.getfloat('z_live_speed', 1.25, above=0.)
        self.xy_probe_z = config.getfloat('xy_probe_z')
        self.xy_distance = config.getfloat('xy_probe_distance', 15., above=0.)
        self.xy_speed = config.getfloat('xy_probe_speed', 13.333, above=0.)
        self.xy_slow_speed = config.getfloat('xy_probe_slow_speed', 1.333,
                                             above=0.)
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
        for cmd in ['PROBE_XY_CENTER', 'Z_ENDSTOP_ADJUST', 'QUERY_STALLGUARD',
                    'CAL_START', 'CAL_MOVE', 'CAL_DATUM', 'CAL_HEIGHT',
                    'CAL_SET_ORIGIN', 'CAL_XY', 'CAL_NOZZLE_OFFSET',
                    'CAL_FINISH']:
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
        status['stallguard'] = self.stallguard.get_status()
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
    def _axis_stepper(self, axis, index=None):
        # Driver moving an axis (the active carriage for X)
        if axis == 2:
            return 'stepper_z'
        if axis == 1:
            return 'stepper_y'
        if index is None:
            index = self._active_index()
        return self._dc_rails()[index].get_name()
    def _travel(self, coord, speed, index=None):
        axes = [i for i, c in enumerate(coord) if c is not None]
        self.stallguard.move(coord, speed, [(axis, self._axis_stepper(
            axis, index)) for axis in axes])
    def _activate_carriage(self, index):
        gcode = self.printer.lookup_object('gcode')
        gcode.run_script_from_command("SET_DUAL_CARRIAGE CARRIAGE=%d"
                                      % (index,))
    def _select_carriage(self, index):
        # Make sure the other carriage waits at its endstop (as the stock
        # firmware does before every measurement), so the active nozzle
        # can reach every calibration point
        rails = self._dc_rails()
        other = rails[1 - index]
        park_x = other.rail.get_homing_info().position_endstop
        dc = self.printer.lookup_object('dual_carriage')
        positions = dc.save_dual_carriage_state()['carriage_positions']
        if abs(positions[other.get_name()] - park_x) > .01:
            if self._active_index() != 1 - index:
                self._activate_carriage(1 - index)
            self._travel([park_x], self.travel_speed, 1 - index)
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
        # Stock order (bed_preapare): bed to the preparation height, other
        # carriage parked, then the nozzle above the point
        toolhead = self.printer.lookup_object('toolhead')
        cur_z = toolhead.get_position()[2]
        lift_speed = self.get_probe_params()['lift_speed']
        self.live = None
        if keep_z:
            z = cur_z
            toolhead.manual_move([None, None, cur_z + LIVE_RETRACT],
                                 lift_speed)
        else:
            self._travel([None, None, self.travel_z], lift_speed)
        self._select_carriage(tool)
        self._travel(list(xy), self.travel_speed)
        if z is not None:
            toolhead.manual_move([None, None, z], lift_speed)
    # Calibration touches
    def _limited_target(self, axis, direction, distance):
        toolhead = self.printer.lookup_object('toolhead')
        pos = toolhead.get_position()
        target = list(pos)
        target[axis] += direction * distance
        # Do not leave the travel range (the Z minimum is below the bare
        # bed, as in the stock firmware's apply_motion_limits)
        curtime = self.printer.get_reactor().monotonic()
        status = toolhead.get_status(curtime)
        low = status['axis_minimum'][axis]
        high = status['axis_maximum'][axis]
        target[axis] = min(max(target[axis], low), high)
        return target
    def _touch(self, axis, direction, distance, speed, guarded=False):
        # Stock probe(): approach until the switch closes, then move back
        # until it opens.  Returns the opening position on the axis.
        toolhead = self.printer.lookup_object('toolhead')
        phoming = self.printer.lookup_object('homing')
        endstop = self._switch().mcu_endstop
        axis_name = "XYZ"[axis]
        if endstop.query_endstop(toolhead.get_last_move_time()):
            raise self.printer.command_error(
                "Nozzle switch closed before the %s touch - clean the"
                " nozzle and check the sensor" % (axis_name,))
        target = self._limited_target(axis, direction, distance)
        start = toolhead.get_position()[axis]
        guard = previous = None
        if guarded:
            guard, previous = self._arm_stallguard(axis)
        endstop.stalled = False
        try:
            if guard is not None:
                endstop.guards = [guard]
            phoming.manual_home(toolhead, [(endstop, "probe")], target,
                                speed, probe_pos=True, triggered=True,
                                check_triggered=True)
        except self.printer.command_error as e:
            if endstop.stalled:
                # Steps may have been lost; home again before the next
                # move (stock: xy_need_re_home / z_need_re_home)
                toolhead.get_kinematics().clear_homing_state(
                    axis_name.lower())
                raise self.printer.command_error(
                    "StallGuard stopped the %s axis before the nozzle"
                    " touched - check for obstacles, the build plate and"
                    " the nozzle sensor" % (axis_name,))
            if "No trigger" in str(e):
                raise self.printer.command_error(
                    "No nozzle contact within %.1fmm on the %s axis"
                    % (abs(target[axis] - start), axis_name))
            raise
        finally:
            endstop.guards = []
            if guard is not None:
                self._disarm_stallguard(axis, previous)
        release = list(toolhead.get_position())
        release[axis] = start
        try:
            epos = phoming.manual_home(toolhead, [(endstop, "probe")],
                                       release, speed, probe_pos=True,
                                       triggered=False, check_triggered=True)
        except self.printer.command_error as e:
            if "No trigger" in str(e):
                raise self.printer.command_error(
                    "Nozzle switch did not open after the %s touch - check"
                    " the sensor" % (axis_name,))
            raise
        return epos[axis]
    def _arm_stallguard(self, axis):
        name = self._axis_stepper(axis)
        if not self.stallguard.has(name):
            return None, None
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        line = self.stallguard.lines[name]
        previous = self.stallguard.arm(name)
        if line.is_active():
            # A driver reports an error or the line is stuck; the stock
            # firmware reacts to edges only and probes without guard then
            self.stallguard.disarm(name, previous)
            logging.warning("StallGuard line of %s active before the move,"
                            " probing without StallGuard", name)
            return None, None
        return line, previous
    def _disarm_stallguard(self, axis, previous):
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        self.stallguard.disarm(self._axis_stepper(axis), previous)
    def _multi_touch(self, axis, direction, distance, speed, slow_speed):
        # Stock multiple_probe(): one fast, guarded touch, then slow
        # touches from just above the surface; the mean without the
        # highest and lowest result is the measurement
        toolhead = self.printer.lookup_object('toolhead')
        results = []
        for i in range(self.cal_samples + 1):
            if i == 0:
                pos = self._touch(axis, direction, distance, speed, True)
            else:
                max_delta = 2. * self.max_delta if i == 1 else self.max_delta
                pos = self._touch(axis, direction,
                                  self.backoff + 2. * max_delta, slow_speed)
                results.append(pos)
            backoff = list(toolhead.get_position())
            backoff[axis] = pos - direction * self.backoff
            toolhead.manual_move(backoff, speed)
        results.sort()
        trimmed = results[1:-1]
        return sum(trimmed) / len(trimmed)
    def _probe_z(self):
        # Stock probe_z_offset(): measure the bed below the nozzle and
        # return to the preparation height
        lift_speed = self.get_probe_params()['lift_speed']
        z = self._multi_touch(2, -1., self.z_distance, self.z_speed,
                              self.z_slow_speed)
        self._travel([None, None, self.travel_z], lift_speed)
        return z
    def _live_touch(self):
        # Stock probe_hight_offset(): repeated single touches while the
        # user turns a wheel; the first one is fast and guarded, the next
        # ones slow and only as long as the last change needs
        toolhead = self.printer.lookup_object('toolhead')
        count, last_distance = self.live
        if self._query_endstop(toolhead.get_last_move_time()):
            # The bed was raised into the nozzle meanwhile
            toolhead.manual_move([None, None, toolhead.get_position()[2]
                                  + LIVE_RETRACT], self.z_speed)
            count = 0
        if count == 0:
            distance, speed = self.z_distance, self.z_speed
        else:
            if count == 1:
                max_delta = 2. * self.max_delta
            else:
                max_delta = max(2. * (self.backoff - last_distance),
                                self.max_delta)
            distance, speed = self.backoff + 2. * max_delta, self.z_live_speed
        start = toolhead.get_position()[2]
        try:
            z = self._touch(2, -1., distance, speed, count == 0)
        except self.printer.command_error:
            self.live = None
            if count == 0:
                raise
            # The bed was lowered further than a slow touch reaches -
            # start over with a fast touch
            self.live = (0, 0.)
            return self._live_touch()
        self.live = (count + 1, abs(z - start))
        toolhead.manual_move([None, None, z + self.backoff], self.z_speed)
        return z
    # Horizontal probing
    def _probe_xy_center(self, gcmd, tool):
        self._check_homed()
        toolhead = self.printer.lookup_object('toolhead')
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
            epos = phoming.manual_home(toolhead, endstops, target, self.z_speed,
                                       probe_pos=True, triggered=True,
                                       check_triggered=False)
            if epos[2] > probe_z + 0.01:
                toolhead.manual_move([None, None, self.travel_z],
                                     self.z_speed)
                raise gcmd.error("Nozzle contact at Z=%.3f before reaching"
                                 " the calibration height - remove the"
                                 " build plate" % (epos[2],))
            center = []
            for axis in (0, 1):
                low = self._multi_touch(axis, -1., self.xy_distance,
                                        self.xy_speed, self.xy_slow_speed)
                toolhead.manual_move([cx, cy], self.xy_speed)
                high = self._multi_touch(axis, 1., self.xy_distance,
                                         self.xy_speed, self.xy_slow_speed)
                toolhead.manual_move([cx, cy], self.xy_speed)
                center.append(.5 * (low + high))
            toolhead.manual_move([None, None, self.travel_z], self.z_speed)
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
    cmd_SNAPMAKER_QUERY_STALLGUARD_help = (
        "Report the StallGuard thresholds and DIAG line states")
    def cmd_SNAPMAKER_QUERY_STALLGUARD(self, gcmd):
        sg = self.stallguard
        if not sg.lines:
            gcmd.respond_info("StallGuard is not configured")
            return
        msg = []
        for name, line in sg.lines.items():
            measured = sg.measured.get(name)
            source = ("fixed" if name in sg.fixed else
                      "default" if measured is None else
                      "from SG_RESULT %d" % (measured,))
            msg.append("%s: threshold %d (%s), DIAG %s %s"
                       % (name, sg.thresholds[name], source, line.pin,
                          "active" if line.is_active() else "inactive"))
        gcmd.respond_info("\n".join(msg))
    # Z origin
    def _z_rail(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        return [r for r in kin.rails if r.get_name() == 'stepper_z'][0]
    def _store_z_origin(self, gcmd, offset):
        # The bed homes to the Z maximum, so its endstop position doubles
        # as the travel limit and both must move together
        endstop = self._z_rail().get_homing_info().position_endstop - offset
        # Not Klipper's usual "The SAVE_CONFIG command will ..." text:
        # KlipperScreen asks to save on any message naming SAVE_CONFIG, and
        # the calibration menu saves by itself
        gcmd.respond_info(
            "stepper_z: position_endstop: %.3f\n"
            "Stored in printer.cfg when the configuration is saved"
            % (endstop,))
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
        self.live = None
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
        "Probe the bare bed with the left nozzle as height reference"
        " (POINT= ORIGIN=0 to keep the Z origin)")
    def cmd_SNAPMAKER_CAL_DATUM(self, gcmd):
        # The stock bed leveling also derives the Z origin from this
        # reference (the print surface is the bed surface plus the plate
        # thickness); its nozzle height calibration does not
        self._check_session()
        self._check_homed()
        self._set_power(True)
        self._move_to(self._point(gcmd), 0)
        self.datum = self._probe_z()
        self.height_difference = None
        if gcmd.get_int('ORIGIN', 1):
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
        at_point = (self.live is not None and self._active_index() == tool
                    and abs(pos[0] - xy[0]) < .01 and abs(pos[1] - xy[1]) < .01)
        if not at_point:
            self._move_to(xy, tool)
            self.live = (0, 0.)
        self.height_difference = self._live_touch() - self.datum
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
