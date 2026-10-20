# Snapmaker J1 power loss detection and print recovery
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, json, logging

CHECKPOINT_TIME = 0.250
CHECKPOINT_HISTORY = 64
ABNORMAL_SIGNAL_TIME = 1.

# The J1 power supply reports a mains failure on a dedicated input.  The
# remaining energy is enough to stop the machine, but not to finish the
# queued moves.  While printing, this module records which file position
# belongs to the moves that have actually been executed, so that a print
# can be resumed after the power returns.  The recovery state is written
# when the mains failure is detected, on every layer change and at a
# regular interval (in case the host loses power first).
class SnapmakerJ1PowerLoss:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.filename = os.path.expanduser(config.get('filename'))
        self.save_interval = config.getfloat('save_interval', 30., minval=0.)
        self.save_objects = config.getlist('save_objects', [])
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.resume_gcode = gcode_macro.load_template(config, 'resume_gcode')
        buttons = self.printer.load_object(config, 'buttons')
        buttons.register_debounce_button(config.get('sense_pin'),
                                         self._sense_handler, config)
        self.printer.load_object(config, 'virtual_sdcard')
        # State
        self.enabled = True
        self.signal_state = False
        self.print_seen = False
        self.checkpoints = []
        self.next_save_time = 0.
        self.last_saved_z = None
        self.pending = self._load()
        self.checkpoint_timer = None
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('idle_timeout:printing',
                                            self._handle_printing)
        self.printer.register_event_handler('virtual_sdcard:reset_file',
                                            self._handle_reset_file)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('SNAPMAKER_POWER_LOSS_RESUME',
                               self.cmd_SNAPMAKER_POWER_LOSS_RESUME,
                               desc=self.cmd_SNAPMAKER_POWER_LOSS_RESUME_help)
        gcode.register_command('SNAPMAKER_POWER_LOSS_CLEAR',
                               self.cmd_SNAPMAKER_POWER_LOSS_CLEAR,
                               desc=self.cmd_SNAPMAKER_POWER_LOSS_CLEAR_help)
        gcode.register_command('SNAPMAKER_POWER_LOSS_STATUS',
                               self.cmd_SNAPMAKER_POWER_LOSS_STATUS,
                               desc=self.cmd_SNAPMAKER_POWER_LOSS_STATUS_help)
    # Persistent state
    def _load(self):
        try:
            with open(self.filename, 'r') as f:
                return json.load(f)
        except IOError:
            return None
        except ValueError:
            logging.exception("Unable to parse power loss state %s",
                              self.filename)
            return None
    def _write(self, state):
        tmpname = self.filename + ".tmp"
        try:
            with open(tmpname, 'w') as f:
                json.dump(state, f)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmpname, self.filename)
        except (IOError, OSError):
            logging.exception("Unable to write power loss state %s",
                              self.filename)
    def _remove(self):
        self.pending = None
        try:
            os.remove(self.filename)
        except OSError:
            pass
    # Event handling
    def _handle_ready(self):
        self.checkpoint_timer = self.reactor.register_timer(
            self._checkpoint_event)
        # A sense input that stays active after startup indicates a wiring
        # or hardware problem - do not act on it (as the stock firmware)
        self.reactor.register_timer(self._check_abnormal_signal,
                                    self.reactor.monotonic()
                                    + ABNORMAL_SIGNAL_TIME)
    def _check_abnormal_signal(self, eventtime):
        if self.signal_state:
            self.enabled = False
            logging.warning("Power loss signal active at startup -"
                            " power loss detection disabled")
        return self.reactor.NEVER
    def _handle_printing(self, print_time):
        self.reactor.update_timer(self.checkpoint_timer, self.reactor.NOW)
    def _handle_reset_file(self):
        self.checkpoints = []
        self.last_saved_z = None
        self._remove()
    def _sdcard(self):
        return self.printer.lookup_object('virtual_sdcard')
    def _is_printing(self, eventtime):
        sdcard = self._sdcard()
        return sdcard.is_active() and sdcard.file_path() is not None
    def _snapshot(self, eventtime):
        sdcard = self._sdcard()
        if sdcard.is_cmd_from_sd():
            # The command being run has already queued its moves
            file_position = sdcard.get_file_position()
        else:
            file_position = sdcard.get_status(eventtime)['file_position']
        toolhead = self.printer.lookup_object('toolhead')
        gcode_move = self.printer.lookup_object('gcode_move')
        gstate = gcode_move.get_status(eventtime)
        state = {
            'file_path': sdcard.file_path(),
            'file_position': file_position,
            'extruder': toolhead.get_extruder().get_name(),
            'position': list(gstate['position']),
            'gcode_position': list(gstate['gcode_position']),
            'homing_origin': list(gstate['homing_origin']),
            'speed': gstate['speed'],
            'speed_factor': gstate['speed_factor'],
            'extrude_factor': gstate['extrude_factor'],
            'absolute_coordinates': gstate['absolute_coordinates'],
            'absolute_extrude': gstate['absolute_extrude'],
            'heaters': {}, 'objects': {}}
        pheaters = self.printer.lookup_object('heaters')
        for name in pheaters.get_status(eventtime)['available_heaters']:
            heater = self.printer.lookup_object(name)
            state['heaters'][name] = heater.get_status(eventtime)['target']
        dc = self.printer.lookup_object('dual_carriage', None)
        if dc is not None:
            state['dual_carriage'] = dc.get_status(eventtime)['carriages']
        print_stats = self.printer.lookup_object('print_stats')
        state['print_duration'] = print_stats.get_status(
            eventtime)['print_duration']
        for name in self.save_objects:
            obj = self.printer.lookup_object(name, None)
            if obj is not None and hasattr(obj, 'get_status'):
                state['objects'][name] = obj.get_status(eventtime)
        return state
    def _note_executed(self, print_time, state):
        state['print_time'] = print_time
        self.checkpoints.append(state)
        del self.checkpoints[:-CHECKPOINT_HISTORY]
    def _executed_state(self, eventtime):
        # Find the last checkpoint whose moves have completed
        mcu = self.printer.lookup_object('mcu')
        print_time = mcu.estimated_print_time(eventtime)
        done = [s for s in self.checkpoints if s['print_time'] <= print_time]
        if done:
            return done[-1]
        return None
    def _checkpoint_event(self, eventtime):
        if not self._is_printing(eventtime):
            if not self.print_seen:
                # Other activity (eg homing before a recovery) must not
                # discard a stored state
                return self.reactor.NEVER
            # A finished or cancelled print needs no recovery (a paused or
            # failed one may still be resumed)
            print_stats = self.printer.lookup_object('print_stats')
            state = print_stats.get_status(eventtime)['state']
            if state == 'paused':
                return eventtime + CHECKPOINT_TIME
            self.print_seen = False
            if state in ('complete', 'cancelled', 'standby'):
                self.checkpoints = []
                self._remove()
            return self.reactor.NEVER
        self.print_seen = True
        state = self._snapshot(eventtime)
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.register_lookahead_callback(
            lambda print_time: self._note_executed(print_time, state))
        executed = self._executed_state(eventtime)
        if executed is not None:
            z = executed['position'][2]
            layer_change = (self.last_saved_z is not None
                            and abs(z - self.last_saved_z) > 0.0001)
            interval_done = (self.save_interval
                             and eventtime >= self.next_save_time)
            if layer_change or interval_done or self.last_saved_z is None:
                self._save(executed, 'checkpoint')
                self.last_saved_z = z
                self.next_save_time = eventtime + self.save_interval
        return eventtime + CHECKPOINT_TIME
    def _save(self, state, reason):
        state = dict(state)
        state['reason'] = reason
        self.pending = state
        self._write(state)
    def _sense_handler(self, eventtime, state):
        self.signal_state = state
        if not state or not self.enabled:
            return
        if not self._is_printing(eventtime):
            logging.info("Power loss signal while not printing")
            return
        executed = self._executed_state(eventtime)
        # Stop all motion and heating immediately, then store the state
        self.printer.invoke_shutdown("Power loss detected")
        if executed is not None:
            self._save(executed, 'power_loss')
    # G-Code commands
    def get_status(self, eventtime):
        pending = self.pending
        return {'enabled': self.enabled,
                'signal': self.signal_state,
                'pending': pending is not None,
                'file_path': pending['file_path'] if pending else None,
                'file_position': pending['file_position'] if pending else 0,
                'reason': pending['reason'] if pending else None}
    cmd_SNAPMAKER_POWER_LOSS_STATUS_help = "Report the stored recovery state"
    def cmd_SNAPMAKER_POWER_LOSS_STATUS(self, gcmd):
        if self.pending is None:
            gcmd.respond_info("No interrupted print stored")
            return
        p = self.pending
        gcmd.respond_info("Interrupted print (%s): %s at byte %d, Z=%.3f"
                          % (p['reason'], p['file_path'], p['file_position'],
                             p['position'][2]))
    cmd_SNAPMAKER_POWER_LOSS_CLEAR_help = "Discard the stored recovery state"
    def cmd_SNAPMAKER_POWER_LOSS_CLEAR(self, gcmd):
        self._remove()
        gcmd.respond_info("Interrupted print discarded")
    cmd_SNAPMAKER_POWER_LOSS_RESUME_help = "Resume an interrupted print"
    def cmd_SNAPMAKER_POWER_LOSS_RESUME(self, gcmd):
        state = self.pending
        if state is None:
            raise gcmd.error("No interrupted print stored")
        sdcard = self._sdcard()
        if sdcard.is_active():
            raise gcmd.error("A print is already active")
        sdcard_dir = sdcard.sdcard_dirname
        path = state['file_path']
        if not os.path.exists(path):
            raise gcmd.error("File %s no longer exists" % (path,))
        gcode = self.printer.lookup_object('gcode')
        # Restore the machine state, then continue from the stored offset
        context = self.resume_gcode.create_template_context()
        context['state'] = state
        self.resume_gcode.run_gcode_from_command(context)
        relpath = os.path.relpath(path, sdcard_dir)
        gcode.run_script_from_command("M23 %s\nM26 S%d"
                                      % (relpath, state['file_position']))
        self.checkpoints = []
        self.last_saved_z = None
        gcode.run_script_from_command("M24")

def load_config(config):
    return SnapmakerJ1PowerLoss(config)
