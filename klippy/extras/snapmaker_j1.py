# Snapmaker J1 machine support (board revision, nozzle detection,
# heated bed feedback, print file header handling and PID calibration
# without SAVE_CONFIG)
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, logging, threading, importlib.util
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
# Below the target by more than this, a nozzle heats at full power
# without PID (as PID_FUNCTIONAL_RANGE of the stock firmware)
PID_RANGE = 10.
PID_CHECK_TIME = 1.

# Board revision voltage divider on the hw_version_pin (upper bounds)
HW_VERSION_MV = [450., 700., 1400., 2000., 2700., 3200.]
# Revision 1 boards have the mains failure input and the DIAG lines of
# the drivers on other pins; as in the stock firmware, every later
# revision is wired like revision 2.  printer-snapmaker-j1-2022.cfg is
# written for revision 2 and includes this file (next to printer.cfg),
# which Klipper writes on a revision 1 board and removes on a later one.
BOARD_FILE = 'snapmaker_j1_board.cfg'
BOARD_REV1 = """# Written by Klipper: this printer has a revision 1 main board.  Klipper
# checks the revision at every start and rewrites or removes this file
# when the board changes.
[snapmaker_j1]
hardware_version: 1

[snapmaker_j1_power_loss]
sense_pin: ^PC12

[snapmaker_j1_probe]
stallguard_pin_stepper_x: !PE3
stallguard_pin_dual_carriage: !PE3
stallguard_pin_stepper_y: !PE3
stallguard_pin_stepper_z: !PE3
"""
# The print file checks of the IDEX modes, shared with the print dialog of
# the touch screen (plain Python, loaded by its path in the repository)
PRINT_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                          '..', '..', 'scripts', 'snapmaker_j1_print_file.py')
MODE_NAMES = {'FULL_CONTROL': 'IDEX', 'BACKUP': 'Backup',
              'DUPLICATION': 'Duplication', 'MIRROR': 'Mirror'}
# Retraction distance above which a print asks first (stock)
MAX_RETRACTION = 2.
# Files per page of SNAPMAKER_PRINT_MODE (the newest first); more do not
# fit the dialog of Mainsail without scrolling
PM_FILES = 6

def load_print_file():
    spec = importlib.util.spec_from_file_location('snapmaker_j1_print_file',
                                                  PRINT_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# One automatic adjustment per Klipper process (kept over restarts), so a
# reading that changes between starts cannot make Klipper restart again
# and again
board_adjusted = [False]

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
# A hotend is pushed in without a cable, its temperature sensor reads
# open (far above max_temp) while it is out.  The MCU range check would
# shut Klipper down until a FIRMWARE_RESTART; the upper limit is checked
# here instead, and a missing hotend only blocks its heater (as the stock
# firmware).  The MCU keeps checking the lower limit.
TOOL_HEATERS = ['extruder', 'extruder1']
SENSOR_OPEN_TEMP = 1000.
SENSOR_CHECK_TIME = 0.250
SENSOR_OVER_TIME = 1.

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

class ControlPIDRange(heaters.ControlPID):
    # Klipper's PID control with the functional range of the stock
    # firmware (Marlin PID_FUNCTIONAL_RANGE) for the nozzles: more than
    # PID_RANGE below the target the heater runs at full power and the
    # integral is not accumulated.  Klipper integrates the whole way up,
    # unless the output is at its limit; with the slow PT100 of the J1
    # (some seconds dead time) the nozzle then overshoots by up to 10C
    # after heating up from standby and takes a minute or more to come
    # back.  The integral keeps its value from before, the power that
    # held the previous (standby) temperature, a good start for the new
    # target.
    def temperature_update(self, read_time, temp, target_temp):
        if not target_temp or target_temp - temp <= PID_RANGE:
            heaters.ControlPID.temperature_update(self, read_time, temp,
                                                  target_temp)
            return
        # As ControlPID, but full power and no integration
        time_diff = read_time - self.prev_temp_time
        temp_diff = temp - self.prev_temp
        if time_diff >= self.min_deriv_time:
            temp_deriv = temp_diff / time_diff
        else:
            temp_deriv = (self.prev_temp_deriv
                          * (self.min_deriv_time - time_diff)
                          + temp_diff) / self.min_deriv_time
        self.heater.set_pwm(read_time, self.heater_max_power)
        self.prev_temp = temp
        self.prev_temp_time = read_time
        self.prev_temp_deriv = temp_deriv

class SnapmakerJ1:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        # Board revision
        self.hw_version = config.getint('hardware_version', minval=1)
        self.board_file = os.path.join(os.path.dirname(
            self.printer.get_start_args()['config_file']), BOARD_FILE)
        self.hw_adc = AnalogInput(config, 'snapmaker_j1_hw_version',
                                  config.get('hw_version_pin'))
        self.detected_hw_version = None
        # Nozzle identification
        self.nozzle_adcs = [
            AnalogInput(config, 'snapmaker_j1_nozzle_t0',
                        config.get('nozzle_id_pin_t0')),
            AnalogInput(config, 'snapmaker_j1_nozzle_t1',
                        config.get('nozzle_id_pin_t1'))]
        self.tool_heaters = []
        self.tool_temps = [0., 0.]
        self.tool_over_since = [None, None]
        self.tool_blocked = [False, False]
        self.nozzle_prompt = False
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._setup_tool_sensors)
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
                             'file': [None, None], 'machine': [None, None],
                             'retraction': 0., 'mode': None,
                             'x_offset': 0.}
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
        # Print mode choice for the web interface (as the print dialog of
        # the touch screen): the file, its analysis and a busy flag
        self.pm = {'filename': None, 'info': None, 'busy': False}
        for name in ('DIALOG', 'START', 'CANCEL'):
            self.gcode.register_command(
                '_SNAPMAKER_PRINT_MODE_' + name,
                getattr(self, 'cmd_SNAPMAKER_PRINT_MODE_' + name))
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
        self.reactor.register_timer(self._check_tool_sensors,
                                    self.reactor.NOW)
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
        if (self.detected_hw_version == 1) == (self.hw_version == 1):
            return self.reactor.NEVER
        if self._adjust_board_file(self.detected_hw_version):
            return self.reactor.NEVER
        self.printer.invoke_shutdown(
            "Snapmaker J1 board revision %d detected, but the"
            " configuration is for revision %d - set hardware_version"
            " and the revision dependent pins (sense_pin of"
            " [snapmaker_j1_power_loss], stallguard_pin_* of"
            " [snapmaker_j1_probe])"
            % (self.detected_hw_version, self.hw_version))
        return self.reactor.NEVER
    # Write (revision 1) or remove (later revisions) the board file and
    # restart, so the configuration matches the board.  False when that
    # cannot help: already done once, the file is already as needed (the
    # revision is set elsewhere) or a heater is on
    def _adjust_board_file(self, detected):
        if board_adjusted[0]:
            return False
        pheaters = self.printer.lookup_object('heaters')
        eventtime = self.reactor.monotonic()
        for heater in pheaters.get_all_heaters():
            if pheaters.lookup_heater(heater).get_status(
                    eventtime)['target']:
                return False
        try:
            current = None
            if os.path.exists(self.board_file):
                with open(self.board_file) as f:
                    current = f.read()
            if detected == 1:
                if current == BOARD_REV1:
                    return False
                tmp = self.board_file + '.tmp'
                with open(tmp, 'w') as f:
                    f.write(BOARD_REV1)
                os.rename(tmp, self.board_file)
            else:
                if current is None:
                    return False
                os.remove(self.board_file)
        except (IOError, OSError):
            logging.exception("Snapmaker J1: cannot update %s",
                              self.board_file)
            return False
        board_adjusted[0] = True
        msg = ("Snapmaker J1 board revision %d detected: configuration"
               " adjusted, restarting" % (detected,))
        logging.info(msg)
        self.gcode.respond_info(msg)
        # The micro-controller gets other pins: a plain restart would stop
        # at the changed MCU configuration
        self.printer.request_exit('firmware_restart')
        return True
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
    # Hotend temperature sensors (the heaters exist once the config is read)
    def _setup_tool_sensors(self):
        pheaters = self.printer.lookup_object('heaters')
        for index, name in enumerate(TOOL_HEATERS):
            heater = pheaters.lookup_heater(name)
            heater.sensor.setup_minmax(heater.min_temp, SENSOR_OPEN_TEMP)
            def temperature_callback(read_time, temp, index=index,
                                     callback=heater.temperature_callback):
                self.tool_temps[index] = temp
                callback(read_time, temp)
            heater.sensor.setup_callback(temperature_callback)
            def set_temp(degrees, index=index, set_temp=heater.set_temp):
                if degrees and self._tool_open(index):
                    raise self.printer.command_error(
                        "%s not detected. Insert the hotend."
                        % (NOZZLE_NAMES[index],))
                set_temp(degrees)
            heater.set_temp = set_temp
            self.tool_heaters.append(heater)
    def _show_nozzle_prompt(self):
        # A dialog on the display (action:prompt, also in Mainsail and
        # Fluidd) while a hotend is missing; it closes once all are back
        missing = [NOZZLE_NAMES[i] for i in range(2) if self.tool_blocked[i]]
        if not missing:
            if self.nozzle_prompt:
                self.nozzle_prompt = False
                self.gcode.respond_raw("// action:prompt_end")
            return
        self.nozzle_prompt = True
        for line in [
                "action:prompt_begin Nozzle Missing",
                "action:prompt_text %s not detected. Insert the hotend, its"
                " heater stays off until then." % (" and ".join(missing),),
                "action:prompt_footer_button Close"
                "|RESPOND TYPE=command MSG=action:prompt_end",
                "action:prompt_show"]:
            self.gcode.respond_raw("// " + line)
    def _tool_open(self, index):
        return (self.tool_blocked[index] or self.tool_temps[index]
                > self.tool_heaters[index].max_temp)
    def _check_tool_sensors(self, eventtime):
        for index, heater in enumerate(self.tool_heaters):
            name = NOZZLE_NAMES[index]
            if self.tool_temps[index] <= heater.max_temp:
                self.tool_over_since[index] = None
                if (self.tool_blocked[index]
                    and self._nozzle_info(index)['material'] is not None):
                    self.tool_blocked[index] = False
                    self.gcode.respond_info("%s detected" % (name,))
                    self._show_nozzle_prompt()
                continue
            if self.tool_over_since[index] is None:
                self.tool_over_since[index] = eventtime
            if eventtime - self.tool_over_since[index] < SENSOR_OVER_TIME:
                continue
            missing = name in self._missing_nozzles()
            state = self.printer.lookup_object('print_stats').get_status(
                eventtime)['state']
            if missing and state != 'printing':
                if not self.tool_blocked[index]:
                    self.tool_blocked[index] = True
                    heater.set_temp(0.)
                    self.gcode.respond_info(
                        "%s not detected. Insert the hotend." % (name,))
                    self._show_nozzle_prompt()
                continue
            self.printer.invoke_shutdown(
                "Heater %s temperature %.1f above max_temp %.1f"
                % (heater.get_name(), self.tool_temps[index],
                   heater.max_temp))
            return self.reactor.NEVER
        return eventtime + SENSOR_CHECK_TIME
    def _handle_shutdown(self):
        # A hotend removed while printing also opens its temperature sensor,
        # which shuts down Klipper with a generic message
        missing = self._missing_nozzles()
        if not missing:
            return
        msg, category = self.printer.get_state_message()
        self.printer.update_error_msg(msg, (
            "%s not detected. Insert the hotend.\n%s"
            % (" and ".join(missing), msg)))
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
            if section.get('control') != 'pid':
                continue
            self.pid_defaults[short] = [
                section['pid_kp'], section['pid_ki'], section['pid_kd']]
            gains = variables.get(PID_VARIABLE % (short,))
            if gains is not None:
                self.pid_stored.add(short)
            else:
                gains = self.pid_defaults[short]
            # Also with the gains of printer.cfg: the nozzles get the
            # functional range (ControlPIDRange)
            self._set_pid_gains(pheaters.lookup_heater(name), *gains)
    def _set_pid_gains(self, heater, Kp, Ki, Kd):
        control = heaters.ControlPID
        if heater.get_name().startswith('extruder'):
            control = ControlPIDRange
        heater.set_control(control(heater, PIDGains(Kp, Ki, Kd)))
    def _lookup_idle_heater(self, gcmd, calibrate=False):
        pheaters = self.printer.lookup_object('heaters')
        try:
            heater = pheaters.lookup_heater(gcmd.get('HEATER'))
        except self.printer.config_error as e:
            raise gcmd.error(str(e))
        eventtime = self.reactor.monotonic()
        if not heater.get_status(eventtime)['target']:
            return heater
        # Changing the control switches the heater off.  A calibration
        # takes over a heater that is only heated (KlipperScreen's PID
        # button sits next to the target temperature, which is usually
        # set first), but never in a print
        state = self.printer.lookup_object('print_stats').get_status(
            eventtime)['state']
        if not calibrate or state in ('printing', 'paused'):
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
        heater = self._lookup_idle_heater(gcmd, calibrate=True)
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
    def _print_paused(self, eventtime):
        # Time the current (or last) print spent paused; print_stats only
        # reports total_duration with the pauses and print_duration without
        # them and without the heating before the first extrusion.  The
        # touch screen shows total_duration minus this as the elapsed time
        stats = self.printer.lookup_object('print_stats', None)
        if stats is None:
            return 0.
        paused = getattr(stats, 'prev_pause_duration', 0.)
        last_pause = getattr(stats, 'last_pause_time', None)
        if last_pause is not None \
                and getattr(stats, 'print_start_time', None) is not None:
            paused += eventtime - last_pause
        return paused
    def get_status(self, eventtime):
        return {'hardware_version': self.hw_version,
                'print_paused': self._print_paused(eventtime),
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
        # Stock: a retraction above 2 mm gets a warning in the same way
        # (read from the slicer settings at the start and end of the file)
        retraction = [None, None]
        try:
            sdcard = self.printer.lookup_object('virtual_sdcard')
            retraction = load_print_file().quick_check(os.path.join(
                sdcard.sdcard_dirname, filename.lstrip('/')))['retraction']
        except (IOError, OSError):
            logging.exception("Reading the retraction of %s", filename)
        too_long = [r for r in retraction
                    if r is not None and r > MAX_RETRACTION]
        # The print mode chosen on the touch screen, for the print after
        # the dialog
        mode = gcmd.get('MODE', None)
        self.nozzle_check = {'filename': filename, 'mismatch': mismatch,
                             'file': file_diameters, 'machine': machine,
                             'retraction': max(too_long) if too_long else 0.,
                             'mode': mode.upper() if mode else None,
                             'x_offset': gcmd.get_float('X_OFFSET', 0.)}
        if mismatch:
            def fmt(d):
                return "?" if d is None else "%.1f mm" % (d,)
            gcmd.respond_info(
                "Nozzle diameter mismatch - file: L %s, R %s; machine:"
                " L %s, R %s" % (fmt(file_diameters[0]),
                                 fmt(file_diameters[1]),
                                 fmt(machine[0]), fmt(machine[1])))

    # Print mode choice (SNAPMAKER_PRINT_MODE in snapmaker-j1-macros.cfg).
    # Reading a large file takes seconds on the display module: it runs in
    # a thread, the dialog (action:prompt) follows from the reactor
    def _pm_gcodes(self):
        return self.printer.lookup_object('virtual_sdcard').sdcard_dirname
    def _pm_files(self):
        # All print files, the newest first (relative to the gcodes folder)
        gcodes = self._pm_gcodes()
        found = []
        for root, dirs, files in os.walk(gcodes):
            top = os.path.normpath(root) == os.path.normpath(gcodes)
            # Not the calibration prints and the copies of this add-on
            dirs[:] = [d for d in dirs if not d.startswith('.')
                       and not (top and d == 'snapmaker_j1')]
            for name in files:
                if not name.lower().endswith(('.gcode', '.gco', '.g')):
                    continue
                path = os.path.join(root, name)
                rel = os.path.relpath(path, gcodes).replace(os.sep, '/')
                # A name the dialog buttons cannot carry
                if '"' in rel or '|' in rel:
                    continue
                found.append((os.path.getmtime(path), rel))
        found.sort(reverse=True)
        return [rel for mtime, rel in found]
    def _pm_check_idle(self, gcmd):
        sdcard = self.printer.lookup_object('virtual_sdcard')
        if sdcard.is_active() or self.pm['busy']:
            raise gcmd.error("Not possible while printing")
    def _pm_thread(self, work, done):
        # work() in a thread, then done(result) in the reactor
        self.pm['busy'] = True
        reactor = self.reactor
        def run():
            try:
                result = work()
            except Exception:
                logging.exception("Snapmaker J1 print mode")
                result = None
            reactor.register_async_callback(
                lambda eventtime: self._pm_done(done, result))
        threading.Thread(target=run, daemon=True).start()
    def _pm_done(self, done, result):
        self.pm['busy'] = False
        try:
            done(result)
        except self.printer.command_error as e:
            self.gcode.respond_info(str(e))
    def _pm_prompt(self, lines):
        for line in lines:
            self.gcode.respond_raw("// action:" + line)
    def cmd_SNAPMAKER_PRINT_MODE_DIALOG(self, gcmd):
        self._pm_check_idle(gcmd)
        pf = load_print_file()
        filename = gcmd.get('FILENAME', '').strip().lstrip('/')
        if not filename:
            # First the file: a page of the files, the newest first (the
            # theme of the web interface shows them as a list)
            files = self._pm_files()
            if not files:
                raise gcmd.error("No print file found")
            page = gcmd.get_int('PAGE', 0, minval=0)
            pages = (len(files) + PM_FILES - 1) // PM_FILES
            page = min(page, pages - 1)
            gcodes = self._pm_gcodes()
            title = "Which file do you want to print?"
            if pages > 1:
                title += " (page %d of %d)" % (page + 1, pages)
            lines = ["prompt_begin Print Mode", "prompt_text " + title]
            for f in files[page * PM_FILES:(page + 1) * PM_FILES]:
                lines.append('prompt_button %s|_SNAPMAKER_PRINT_MODE_DIALOG'
                             ' FILENAME="%s"|secondary'
                             % (pf.short_name(f, 60), f))
                try:
                    info = pf.summary(os.path.join(gcodes, f))
                except (IOError, OSError):
                    info = ""
                lines.append("prompt_text " + (info or " "))
            if page > 0:
                lines.append("prompt_footer_button Newer|"
                             "_SNAPMAKER_PRINT_MODE_DIALOG PAGE=%d"
                             % (page - 1,))
            if page + 1 < pages:
                lines.append("prompt_footer_button Older|"
                             "_SNAPMAKER_PRINT_MODE_DIALOG PAGE=%d"
                             % (page + 1,))
            lines += ["prompt_footer_button Cancel"
                      "|_SNAPMAKER_PRINT_MODE_CANCEL", "prompt_show"]
            self._pm_prompt(lines)
            return
        self._pm_prompt(["prompt_end"])
        path = os.path.join(self._pm_gcodes(), filename)
        if not os.path.isfile(path):
            raise gcmd.error("Print file %s not found" % (filename,))
        gcmd.respond_info("Checking %s..." % (filename,))
        def done(info):
            if info is None:
                raise self.printer.command_error(
                    "The file %s could not be read" % (filename,))
            self.pm.update(filename=filename, info=info)
            lines = ["prompt_begin Print Mode",
                     "prompt_text %s - mode of the file: %s"
                     % (filename, MODE_NAMES[info['mode']])]
            buttons = []
            for mode in pf.MODES:
                reason = pf.check_mode(info, mode)
                if reason:
                    lines.append("prompt_text %s: %s"
                                 % (MODE_NAMES[mode], reason))
                    continue
                style = 'primary' if mode == info['mode'] else 'secondary'
                buttons.append(
                    "prompt_button %s|_SNAPMAKER_PRINT_MODE_START MODE=%s|%s"
                    % (MODE_NAMES[mode], mode, style))
            lines += ["prompt_button_group_start"] + buttons + [
                "prompt_button_group_end",
                "prompt_footer_button Other File|_SNAPMAKER_PRINT_MODE_DIALOG",
                "prompt_footer_button Cancel|_SNAPMAKER_PRINT_MODE_CANCEL",
                "prompt_show"]
            self._pm_prompt(lines)
        self._pm_thread(lambda: pf.analyze(path), done)
    def cmd_SNAPMAKER_PRINT_MODE_CANCEL(self, gcmd):
        self.pm['info'] = None
        self._pm_prompt(["prompt_end"])
    def cmd_SNAPMAKER_PRINT_MODE_START(self, gcmd):
        self._pm_prompt(["prompt_end"])
        self._pm_check_idle(gcmd)
        pf = load_print_file()
        filename, info = self.pm['filename'], self.pm['info']
        mode = gcmd.get('MODE').upper()
        if info is None or mode not in pf.MODES:
            raise gcmd.error(
                "Choose the print mode with SNAPMAKER_PRINT_MODE first")
        reason = pf.check_mode(info, mode)
        if reason:
            raise gcmd.error(reason)
        self.pm['info'] = None
        if mode == info['mode']:
            self.gcode.run_script_from_command(
                'SDCARD_PRINT_FILE FILENAME="%s"' % (filename,))
            return
        offset = pf.x_offset(info, mode)
        if not offset or info['layer_pos'] is None:
            self.gcode.run_script_from_command(
                'SDCARD_PRINT_FILE FILENAME="%s" MODE=%s X_OFFSET=%.2f'
                % (filename, mode, offset))
            return
        # The model moves from its first layer on: a copy of the file
        gcmd.respond_info("Preparing the print...")
        gcodes = self._pm_gcodes()
        def done(copy):
            if copy is None:
                raise self.printer.command_error(
                    "The print could not be prepared")
            self.gcode.run_script(
                'SDCARD_PRINT_FILE FILENAME="%s" MODE=%s X_OFFSET=0'
                % (copy, mode))
        self._pm_thread(lambda: pf.make_copy(filename, info['layer_pos'],
                                             offset, gcodes), done)

def load_config(config):
    return SnapmakerJ1(config)
