# Snapmaker J1 machine support (board revision, nozzle detection,
# heated bed feedback, print file header handling and PID calibration
# without SAVE_CONFIG)
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, logging
from . import heaters, pid_calibrate

ADC_REPORT_TIME = 0.500
ADC_SAMPLE_TIME = 0.001
ADC_SAMPLE_COUNT = 8
ADC_VREF = 3.3
BED_CHECK_TIME = 0.500
PRINT_CHECK_TIME = 1.
# The header of J1 slicer files starts with a thumbnail of several KiB;
# Prusa/Orca style slicers write their settings to the end of the file
FILE_HEADER_LIMIT = 512 * 1024
FILE_TAIL_SIZE = 128 * 1024
# PID gains of a heater from PID_CALIBRATE (save_variables), used instead
# of those in printer.cfg
PID_VARIABLE = 'snap_j1_pid_%s'
# Temperature peaks Klipper's autotune measures before it is done
PID_PEAKS = 12
PID_CHECK_TIME = 1.

# Board revision voltage divider on the hw_version_pin (upper bounds)
HW_VERSION_MV = [450., 700., 1400., 2000., 2700., 3200.]

# Toolhead identification resistor (min mV, max mV, material, diameter)
NOZZLE_TYPES = [
    (0., 100., 'brass', 0.4),
    (116., 316., 'brass', 0.2),
    (390., 590., 'brass', 0.6),
    (698., 898., 'brass', 0.8),
    (1015., 1215., 'hardened_steel', 0.4),
]
NOZZLE_NAMES = ["Nozzle L", "Nozzle R"]
NOZZLE_TOLERANCE = 0.01

# Header lines with the nozzle diameter of a tool: J1 profiles of Luban
# ("Extruder 0 Nozzle Size:0.4"), older Luban versions
# ("nozzle_0_diameter(mm): 0.4") and Cura ("EXTRUDER_TRAIN.0.NOZZLE.DIAMETER")
FILE_NOZZLE_KEYS = ['Extruder %d Nozzle Size', 'nozzle_%d_diameter(mm)',
                    'nozzle_%d_diameter', 'EXTRUDER_TRAIN.%d.NOZZLE.DIAMETER']

# Values of the ";Extruder Mode:" header line written by the J1 slicer
# profiles, mapped to the print modes of the J1 macros
FILE_MODES = {
    'Default': 'FULL_CONTROL', 'Normal': 'FULL_CONTROL',
    'IDEX Full Control': 'FULL_CONTROL', 'IDEX Duplication': 'DUPLICATION',
    'IDEX Mirror': 'MIRROR', 'IDEX Backup': 'BACKUP',
}

class AnalogInput:
    def __init__(self, config, name, pin):
        printer = config.get_printer()
        ppins = printer.lookup_object('pins')
        self.mcu_adc = ppins.setup_pin('adc', pin)
        self.mcu_adc.setup_adc_sample(ADC_REPORT_TIME, ADC_SAMPLE_TIME,
                                      ADC_SAMPLE_COUNT)
        self.mcu_adc.setup_adc_callback(self._adc_callback)
        query_adc = printer.load_object(config, 'query_adc')
        query_adc.register_adc(name, self.mcu_adc)
        self.value = None
    def _adc_callback(self, samples):
        # Batches of (print time, value), the last one is the newest
        self.value = samples[-1][1]
    def get_mv(self):
        if self.value is None:
            return None
        return self.value * ADC_VREF * 1000.

class PIDGains:
    # The config section ControlPID reads its gains from
    def __init__(self, Kp, Ki, Kd):
        self.gains = {'pid_Kp': Kp, 'pid_Ki': Ki, 'pid_Kd': Kd}
    def getfloat(self, option, *args, **kwargs):
        return self.gains[option]

class SnapmakerJ1:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        # Board revision
        self.hw_version = config.getint('hardware_version', minval=1)
        self.hw_adc = AnalogInput(config, 'snapmaker_j1_hw_version',
                                  config.get('hw_version_pin'))
        self.detected_hw_version = None
        # Nozzle identification
        self.nozzle_adcs = [
            AnalogInput(config, 'snapmaker_j1_nozzle_t0',
                        config.get('nozzle_id_pin_t0')),
            AnalogInput(config, 'snapmaker_j1_nozzle_t1',
                        config.get('nozzle_id_pin_t1'))]
        # Heated bed switching feedback
        self.bed_feedback_state = None
        self.bed_check_time = config.getfloat('bed_feedback_time', 2.,
                                              above=BED_CHECK_TIME)
        self.bed_mismatch_since = None
        bed_feedback_pin = config.get('bed_feedback_pin', None)
        self.bed_feedback_enabled = bed_feedback_pin is not None
        if self.bed_feedback_enabled:
            buttons = self.printer.load_object(config, 'buttons')
            buttons.register_buttons([bed_feedback_pin],
                                     self._bed_feedback_handler)
        self.nozzle_check = {'filename': None, 'mismatch': False,
                             'file': [None, None], 'machine': [None, None]}
        self.print_state = None
        # PID calibration in progress (heater, ControlAutoTune) and its
        # abort request, which comes through the API while the calibration
        # holds the g-code queue
        self.pid_tune = None
        self.pid_abort = False
        self.pid_defaults = {}
        self.pid_stored = set()
        self.printer.lookup_object('webhooks').register_endpoint(
            'snapmaker_j1/pid_abort', self._handle_pid_abort)
        self.printer.register_event_handler('klippy:connect',
                                            self._load_pid_gains)
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('klippy:shutdown',
                                            self._handle_shutdown)
        self.gcode.register_command(
            'SNAPMAKER_QUERY_HARDWARE', self.cmd_SNAPMAKER_QUERY_HARDWARE,
            desc=self.cmd_SNAPMAKER_QUERY_HARDWARE_help)
        self.gcode.register_command(
            'SNAPMAKER_FILE_MODE', self.cmd_SNAPMAKER_FILE_MODE,
            desc=self.cmd_SNAPMAKER_FILE_MODE_help)
        self.gcode.register_command(
            'SNAPMAKER_CHECK_NOZZLES', self.cmd_SNAPMAKER_CHECK_NOZZLES,
            desc=self.cmd_SNAPMAKER_CHECK_NOZZLES_help)
        self.gcode.register_command(
            'SNAPMAKER_PID_RESET', self.cmd_SNAPMAKER_PID_RESET,
            desc=self.cmd_SNAPMAKER_PID_RESET_help)
    def _handle_ready(self):
        # PID_CALIBRATE applies and stores its result itself, so no
        # SAVE_CONFIG (and Klipper restart) is needed.  Replaced once all
        # commands are registered.
        self.gcode.register_command('PID_CALIBRATE', None)
        self.gcode.register_command('PID_CALIBRATE', self.cmd_PID_CALIBRATE,
                                    desc=self.cmd_PID_CALIBRATE_help)
        self.reactor.register_timer(self._check_hw_version,
                                    self.reactor.monotonic() + 2.)
        if self.bed_feedback_enabled:
            self.reactor.register_timer(self._check_bed_feedback,
                                        self.reactor.NOW)
        self.reactor.register_timer(self._check_print_end, self.reactor.NOW)
    # End of a completed print: Klipper runs no G-code at that point, the
    # stock firmware cleans up (heaters off, full control mode, parking)
    def _check_print_end(self, eventtime):
        state = self.printer.lookup_object('print_stats').get_status(
            eventtime)['state']
        if self.print_state == 'printing' and state == 'complete':
            self.reactor.register_callback(self._print_done)
        self.print_state = state
        return eventtime + PRINT_CHECK_TIME
    def _print_done(self, eventtime):
        try:
            self.gcode.run_script("_SNAPMAKER_PRINT_DONE")
        except self.printer.command_error as e:
            logging.warning("End of print: %s", e)
    # Board revision
    def _calc_hw_version(self):
        mv = self.hw_adc.get_mv()
        if mv is None:
            return None
        for i, upper in enumerate(HW_VERSION_MV):
            if mv < upper:
                return i + 1
        return len(HW_VERSION_MV) + 1
    def _check_hw_version(self, eventtime):
        self.detected_hw_version = self._calc_hw_version()
        if self.detected_hw_version is None:
            return eventtime + 1.
        if self.detected_hw_version != self.hw_version:
            self.printer.invoke_shutdown(
                "Snapmaker J1 board revision %d detected, but the"
                " configuration is for revision %d - set hardware_version"
                " and the revision dependent pins (sense_pin of"
                " [snapmaker_j1_power_loss], stallguard_pin_* of"
                " [snapmaker_j1_probe])"
                % (self.detected_hw_version, self.hw_version))
        return self.reactor.NEVER
    # Nozzle identification
    def _nozzle_info(self, index):
        mv = self.nozzle_adcs[index].get_mv()
        info = {'adc_mv': mv, 'material': None, 'diameter': None}
        if mv is None:
            return info
        for min_mv, max_mv, material, diameter in NOZZLE_TYPES:
            if min_mv <= mv <= max_mv:
                info.update({'material': material, 'diameter': diameter})
                break
        return info
    def _missing_nozzles(self):
        # The identification resistor reads out of range without a hotend
        # (stock: "nozzle loss", heating of the nozzle is blocked)
        return [NOZZLE_NAMES[i] for i in range(2)
                if self.nozzle_adcs[i].get_mv() is not None
                and self._nozzle_info(i)['material'] is None]
    def _handle_shutdown(self):
        # A missing hotend also opens its temperature sensor, which shuts
        # down Klipper with a generic "ADC out of range" message
        missing = self._missing_nozzles()
        if not missing:
            return
        msg, category = self.printer.get_state_message()
        self.printer.update_error_msg(msg, (
            "%s not detected - check that the hotend is installed and its"
            " cable is plugged in\n%s" % (" and ".join(missing), msg)))
    # Heated bed feedback
    def _bed_feedback_handler(self, eventtime, state):
        self.bed_feedback_state = state
    def _check_bed_feedback(self, eventtime):
        if self.printer.is_shutdown():
            return self.reactor.NEVER
        heater = self.printer.lookup_object('heater_bed')
        power = heater.get_status(eventtime)['power']
        state = self.bed_feedback_state
        mismatch = None
        if power <= 0. and state:
            mismatch = "Heated bed is powered while switched off"
        elif power >= 1. and state is not None and not state:
            mismatch = "Heated bed is not powered while switched on"
        if mismatch is None:
            self.bed_mismatch_since = None
        elif self.bed_mismatch_since is None:
            self.bed_mismatch_since = eventtime
        elif eventtime - self.bed_mismatch_since >= self.bed_check_time:
            self.printer.invoke_shutdown(mismatch)
            return self.reactor.NEVER
        return eventtime + BED_CHECK_TIME
    # Status and commands
    # PID calibration
    def _load_pid_gains(self):
        svv = self.printer.lookup_object('save_variables', None)
        variables = svv.allVariables if svv is not None else {}
        settings = self.printer.lookup_object('configfile').get_status(
            self.reactor.monotonic())['settings']
        pheaters = self.printer.lookup_object('heaters')
        for name in pheaters.get_all_heaters():
            short = name.split()[-1]
            section = settings.get(name, {})
            if section.get('control') == 'pid':
                self.pid_defaults[short] = [
                    section['pid_kp'], section['pid_ki'], section['pid_kd']]
            gains = variables.get(PID_VARIABLE % (short,))
            if gains is not None:
                self._set_pid_gains(pheaters.lookup_heater(name), *gains)
                self.pid_stored.add(short)
    def _set_pid_gains(self, heater, Kp, Ki, Kd):
        heater.set_control(heaters.ControlPID(heater, PIDGains(Kp, Ki, Kd)))
    def _lookup_idle_heater(self, gcmd):
        pheaters = self.printer.lookup_object('heaters')
        try:
            heater = pheaters.lookup_heater(gcmd.get('HEATER'))
        except self.printer.config_error as e:
            raise gcmd.error(str(e))
        # Changing the control switches the heater off
        if heater.get_status(self.reactor.monotonic())['target']:
            raise gcmd.error("Heater %s is in use" % (heater.get_name(),))
        return heater
    def _handle_pid_abort(self, web_request):
        if self.pid_tune is not None:
            self.pid_abort = True
    cmd_PID_CALIBRATE_help = "Run PID calibration test"
    def cmd_PID_CALIBRATE(self, gcmd):
        # As Klipper's PID_CALIBRATE, with the result applied at once and
        # kept in save_variables instead of printer.cfg, and an abort
        # (endpoint snapmaker_j1/pid_abort)
        heater = self._lookup_idle_heater(gcmd)
        target = gcmd.get_float('TARGET')
        short = heater.get_name().split()[-1]
        # Nozzles off the parking wipers (macro of the J1 configuration)
        self.gcode.run_script_from_command(
            "SNAPMAKER_PID_PREPARE HEATER=%s" % (short,))
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.get_last_move_time()
        calibrate = pid_calibrate.ControlAutoTune(heater, target)
        old_control = heater.set_control(calibrate)
        self.pid_tune = (short, calibrate, old_control)
        self.pid_abort = False
        try:
            heater.set_temp(target)
            eventtime = self.reactor.monotonic()
            while (not self.printer.is_shutdown() and not self.pid_abort
                   and heater.check_busy(eventtime)):
                toolhead.get_last_move_time()
                eventtime = self.reactor.pause(eventtime + PID_CHECK_TIME)
        finally:
            heater.set_control(old_control)
            self.pid_tune = None
        if self.pid_abort:
            # Stopped on request, the values stay as they were
            gcmd.respond_info("PID calibration of %s aborted" % (short,))
            return
        if calibrate.check_busy(0., 0., 0.):
            raise gcmd.error("pid_calibrate interrupted")
        Kp, Ki, Kd = calibrate.calc_final_pid()
        logging.info("Autotune: final: Kp=%f Ki=%f Kd=%f", Kp, Ki, Kd)
        Kp, Ki, Kd = [round(v, 3) for v in (Kp, Ki, Kd)]
        self._set_pid_gains(heater, Kp, Ki, Kd)
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=[%.3f,%.3f,%.3f]"
            % (PID_VARIABLE % (short,), Kp, Ki, Kd))
        self.pid_stored.add(short)
        gcmd.respond_info("PID parameters: pid_Kp=%.3f pid_Ki=%.3f pid_Kd=%.3f"
                          "\nApplied and stored" % (Kp, Ki, Kd))
    cmd_SNAPMAKER_PID_RESET_help = "Use the PID values of printer.cfg again"
    def cmd_SNAPMAKER_PID_RESET(self, gcmd):
        heater = self._lookup_idle_heater(gcmd)
        short = heater.get_name().split()[-1]
        if short not in self.pid_defaults:
            raise gcmd.error("%s has no PID values in printer.cfg" % (short,))
        self._set_pid_gains(heater, *self.pid_defaults[short])
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=None" % (PID_VARIABLE % (short,)))
        self.pid_stored.discard(short)
        gcmd.respond_info("PID parameters of %s from printer.cfg: pid_Kp=%.3f"
                          " pid_Ki=%.3f pid_Kd=%.3f"
                          % ((short,) + tuple(self.pid_defaults[short])))
    def _pid_status(self, eventtime):
        gains = {}
        tune = self.pid_tune
        pheaters = self.printer.lookup_object('heaters')
        for name in pheaters.get_all_heaters():
            control = pheaters.lookup_heater(name).control
            if tune and tune[0] == name.split()[-1]:
                # The control the heater gets back after the autotune
                control = tune[2]
            if isinstance(control, heaters.ControlPID):
                gains[name.split()[-1]] = [
                    round(g * heaters.PID_PARAM_BASE, 3)
                    for g in (control.Kp, control.Ki, control.Kd)]
        return {'calibrating': tune[0] if tune else None,
                'progress': (min(1., len(tune[1].peaks) / float(PID_PEAKS))
                             if tune else 0.),
                'gains': gains, 'defaults': dict(self.pid_defaults),
                'stored': sorted(self.pid_stored)}
    def get_status(self, eventtime):
        return {'hardware_version': self.hw_version,
                'detected_hardware_version': self.detected_hw_version,
                'nozzle_t0': self._nozzle_info(0),
                'nozzle_t1': self._nozzle_info(1),
                'nozzle_check': dict(self.nozzle_check),
                'bed_feedback': self.bed_feedback_state,
                'pid': self._pid_status(eventtime)}
    cmd_SNAPMAKER_QUERY_HARDWARE_help = "Report board revision and nozzles"
    def cmd_SNAPMAKER_QUERY_HARDWARE(self, gcmd):
        msg = ["Board revision: configured %d, detected %s (%s mV)"
               % (self.hw_version, self._calc_hw_version(),
                  "%.0f" % self.hw_adc.get_mv()
                  if self.hw_adc.get_mv() is not None else "?")]
        for i in range(2):
            info = self._nozzle_info(i)
            if info['material'] is None:
                desc = "unknown or missing"
            else:
                desc = "%s %.1f mm" % (info['material'], info['diameter'])
            msg.append("T%d nozzle: %s (%s mV)" % (
                i, desc, "%.0f" % info['adc_mv']
                if info['adc_mv'] is not None else "?"))
        gcmd.respond_info("\n".join(msg))
    # Print file header
    def _read_file(self, filename):
        # Returns the comment lines of the file header and of the file end
        sdcard = self.printer.lookup_object('virtual_sdcard')
        path = os.path.join(sdcard.sdcard_dirname, filename.lstrip('/'))
        header, tail = [], []
        try:
            with open(path, 'rb') as f:
                size = 0
                for line in f:
                    size += len(line)
                    line = line.decode('utf-8', 'replace').strip()
                    if line in (';Header End', ';END_OF_HEADER'):
                        break
                    if line and not line.startswith(';'):
                        break
                    header.append(line)
                    if size > FILE_HEADER_LIMIT:
                        break
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - FILE_TAIL_SIZE))
                data = f.read().decode('utf-8', 'replace')
                tail = [l.strip() for l in data.splitlines()
                        if l.startswith(';')]
        except (IOError, OSError):
            logging.exception("Unable to read print file %s", path)
        return header, tail
    def _file_nozzle_diameters(self, header, tail):
        diameters = [None, None]
        for line in header:
            key, sep, value = line[1:].partition(':')
            for i in range(2):
                if key.strip() in [k % (i,) for k in FILE_NOZZLE_KEYS]:
                    try:
                        diameters[i] = float(value.strip())
                    except ValueError:
                        pass
        if diameters == [None, None]:
            # Prusa/Orca style settings: "; nozzle_diameter = 0.4,0.4"
            for line in tail:
                key, sep, value = line[1:].partition('=')
                if key.strip() != 'nozzle_diameter':
                    continue
                for i, v in enumerate(value.split(',')[:2]):
                    try:
                        diameters[i] = float(v.strip())
                    except ValueError:
                        pass
        return diameters
    cmd_SNAPMAKER_FILE_MODE_help = (
        "Select the IDEX print mode from a print file header")
    def cmd_SNAPMAKER_FILE_MODE(self, gcmd):
        header, tail = self._read_file(gcmd.get('FILENAME'))
        mode = None
        for line in header:
            if line.startswith(';Extruder Mode:'):
                mode = FILE_MODES.get(line.split(':', 1)[1].strip())
                break
        if mode is None:
            return
        gcmd.respond_info("Print file requests IDEX mode %s" % (mode,))
        self.gcode.run_script_from_command(
            "SNAPMAKER_SET_PRINT_MODE MODE=%s" % (mode,))
    cmd_SNAPMAKER_CHECK_NOZZLES_help = (
        "Compare the nozzle diameters of a print file with the installed"
        " nozzles")
    def cmd_SNAPMAKER_CHECK_NOZZLES(self, gcmd):
        # Stock: the display asks before printing a file made for other
        # nozzle diameters ("Inconsistent Nozzle Diameter")
        filename = gcmd.get('FILENAME')
        header, tail = self._read_file(filename)
        file_diameters = self._file_nozzle_diameters(header, tail)
        machine = [self._nozzle_info(i)['diameter'] for i in range(2)]
        mismatch = False
        for i in range(2):
            if file_diameters[i] is None:
                continue
            if (machine[i] is None
                or abs(machine[i] - file_diameters[i]) > NOZZLE_TOLERANCE):
                mismatch = True
        self.nozzle_check = {'filename': filename, 'mismatch': mismatch,
                             'file': file_diameters, 'machine': machine}
        if mismatch:
            def fmt(d):
                return "?" if d is None else "%.1f mm" % (d,)
            gcmd.respond_info(
                "Nozzle diameter mismatch - file: L %s, R %s; machine:"
                " L %s, R %s" % (fmt(file_diameters[0]),
                                 fmt(file_diameters[1]),
                                 fmt(machine[0]), fmt(machine[1])))

def load_config(config):
    return SnapmakerJ1(config)
