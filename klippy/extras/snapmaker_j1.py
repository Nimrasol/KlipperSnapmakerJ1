# Snapmaker J1 machine support (board revision, nozzle detection,
# heated bed feedback and print file header handling)
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, logging

ADC_REPORT_TIME = 0.500
ADC_SAMPLE_TIME = 0.001
ADC_SAMPLE_COUNT = 8
ADC_VREF = 3.3
BED_CHECK_TIME = 0.500
FILE_HEADER_SIZE = 8192

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
    def _adc_callback(self, read_time, read_value):
        self.value = read_value
    def get_mv(self):
        if self.value is None:
            return None
        return self.value * ADC_VREF * 1000.

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
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.gcode.register_command(
            'SNAPMAKER_QUERY_HARDWARE', self.cmd_SNAPMAKER_QUERY_HARDWARE,
            desc=self.cmd_SNAPMAKER_QUERY_HARDWARE_help)
        self.gcode.register_command(
            'SNAPMAKER_FILE_MODE', self.cmd_SNAPMAKER_FILE_MODE,
            desc=self.cmd_SNAPMAKER_FILE_MODE_help)
    def _handle_ready(self):
        self.reactor.register_timer(self._check_hw_version,
                                    self.reactor.monotonic() + 2.)
        if self.bed_feedback_enabled:
            self.reactor.register_timer(self._check_bed_feedback,
                                        self.reactor.NOW)
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
    def get_status(self, eventtime):
        return {'hardware_version': self.hw_version,
                'detected_hardware_version': self.detected_hw_version,
                'nozzle_t0': self._nozzle_info(0),
                'nozzle_t1': self._nozzle_info(1),
                'bed_feedback': self.bed_feedback_state}
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
    cmd_SNAPMAKER_FILE_MODE_help = (
        "Select the IDEX print mode from a print file header")
    def cmd_SNAPMAKER_FILE_MODE(self, gcmd):
        filename = gcmd.get('FILENAME')
        sdcard = self.printer.lookup_object('virtual_sdcard')
        path = os.path.join(sdcard.sdcard_dirname, filename.lstrip('/'))
        mode = None
        try:
            with open(path, 'r') as f:
                header = f.read(FILE_HEADER_SIZE)
        except (IOError, OSError, UnicodeDecodeError):
            logging.exception("Unable to read print file header %s", path)
            header = ""
        for line in header.splitlines():
            if line.startswith(';Extruder Mode:'):
                mode = FILE_MODES.get(line.split(':', 1)[1].strip())
                break
        if mode is None:
            return
        gcmd.respond_info("Print file requests IDEX mode %s" % (mode,))
        self.gcode.run_script_from_command(
            "SNAPMAKER_SET_PRINT_MODE MODE=%s" % (mode,))

def load_config(config):
    return SnapmakerJ1(config)
