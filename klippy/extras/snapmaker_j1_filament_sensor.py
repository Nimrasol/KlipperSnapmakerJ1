# Snapmaker J1 analog filament motion sensor
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
from . import filament_switch_sensor

ADC_REPORT_TIME = 0.050
ADC_SAMPLE_TIME = 0.001
ADC_SAMPLE_COUNT = 5
CHECK_TIMEOUT = 0.250

# Stock parameters per board revision (filament_sensor.h, counts of a
# 12 bit reading): threshold, dead space minimum and maximum
REVISION_DEFAULTS = {1: (8., 0., 1433.), 2: (15., 60., 4060.)}

# The J1 filament sensor outputs an analog voltage that changes while
# filament moves through it.  After every check_distance of extrusion
# the reading must have changed by at least `threshold`.  Readings
# close to the ends of the sensor range ("dead space") change little
# even with moving filament, so they only report a problem after an
# additional dead_space_checks checks.

# The enable state (SET_FILAMENT_SENSOR, M412) survives restarts like the
# stock setting stored in the EEPROM
class J1RunoutHelper(filament_switch_sensor.RunoutHelper):
    def __init__(self, config):
        filament_switch_sensor.RunoutHelper.__init__(self, config)
        self.variable = 'snap_j1_%s_enabled' % (self.name,)
    def _handle_ready(self):
        filament_switch_sensor.RunoutHelper._handle_ready(self)
        svv = self.printer.lookup_object('save_variables', None)
        if svv is not None:
            self.sensor_enabled = bool(svv.allVariables.get(self.variable, 1))
    def cmd_SET_FILAMENT_SENSOR(self, gcmd):
        filament_switch_sensor.RunoutHelper.cmd_SET_FILAMENT_SENSOR(self, gcmd)
        self.sensor_enabled = bool(self.sensor_enabled)
        if self.printer.lookup_object('save_variables', None) is not None:
            self.gcode.run_script_from_command(
                "SAVE_VARIABLE VARIABLE=%s VALUE=%d"
                % (self.variable, self.sensor_enabled))

class J1FilamentSensor:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.extruder_name = config.get('extruder')
        revision = 2
        if config.has_section('snapmaker_j1'):
            revision = config.getsection('snapmaker_j1').getint(
                'hardware_version', 2)
        threshold, dead_min, dead_max = REVISION_DEFAULTS.get(
            revision, REVISION_DEFAULTS[2])
        self.check_distance = config.getfloat('check_distance', 3., above=0.)
        self.threshold = config.getfloat('threshold', threshold / 4096.,
                                         above=0.)
        self.check_count = config.getint('check_count', 3, minval=1)
        self.dead_space_min = config.getfloat('dead_space_min',
                                              dead_min / 4096., minval=0.)
        self.dead_space_max = config.getfloat('dead_space_max',
                                              dead_max / 4096., maxval=1.)
        # Stock: 4mm of dead space distance in steps of its 2mm setting
        self.dead_space_count = self.check_count + config.getint(
            'dead_space_checks', 2, minval=0)
        # ADC setup
        ppins = self.printer.lookup_object('pins')
        self.mcu_adc = ppins.setup_pin('adc', config.get('adc_pin'))
        self.mcu_adc.setup_adc_sample(ADC_REPORT_TIME, ADC_SAMPLE_TIME,
                                      ADC_SAMPLE_COUNT)
        self.mcu_adc.setup_adc_callback(self._adc_callback)
        query_adc = self.printer.load_object(config, 'query_adc')
        query_adc.register_adc(config.get_name(), self.mcu_adc)
        self.runout_helper = J1RunoutHelper(config)
        # Internal state
        self.extruder = None
        self.estimated_print_time = None
        self.last_value = None
        self.start_value = None
        self.next_check_pos = None
        self.error_count = self.dead_space_count_now = 0
        self.check_timer = None
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('idle_timeout:printing',
                                            self._handle_printing)
        self.printer.register_event_handler('idle_timeout:ready',
                                            self._handle_not_printing)
        self.printer.register_event_handler('idle_timeout:idle',
                                            self._handle_not_printing)
    def _adc_callback(self, read_time, read_value):
        self.last_value = read_value
    def _handle_ready(self):
        self.extruder = self.printer.lookup_object(self.extruder_name)
        self.estimated_print_time = (
            self.printer.lookup_object('mcu').estimated_print_time)
        self.check_timer = self.reactor.register_timer(self._check_event)
        self.runout_helper.note_filament_present(self.reactor.monotonic(),
                                                 True)
    def _handle_printing(self, print_time):
        self._reset()
        self.reactor.update_timer(self.check_timer, self.reactor.NOW)
    def _handle_not_printing(self, print_time):
        self.reactor.update_timer(self.check_timer, self.reactor.NEVER)
    def _get_extruder_pos(self, eventtime):
        # Filament moved by the extruder motor (its step count, like the
        # stock firmware): unlike the E coordinate it does not jump when
        # the extruder is synced to the other one for duplication
        print_time = self.estimated_print_time(eventtime)
        stepper = self.extruder.extruder_stepper.stepper
        return (stepper.get_past_mcu_position(print_time)
                * stepper.get_step_dist())
    def _reset(self):
        self.start_value = None
        self.error_count = self.dead_space_count_now = 0
        if self.extruder is not None:
            eventtime = self.reactor.monotonic()
            self.next_check_pos = (self._get_extruder_pos(eventtime)
                                   + self.check_distance)
            self.runout_helper.note_filament_present(eventtime, True)
    def _in_dead_space(self, value):
        return value > self.dead_space_max or value < self.dead_space_min
    def _check_event(self, eventtime):
        if self.last_value is None or self.next_check_pos is None:
            return eventtime + CHECK_TIMEOUT
        value = self.last_value
        if self.start_value is None:
            self.start_value = value
            return eventtime + CHECK_TIMEOUT
        epos = self._get_extruder_pos(eventtime)
        if epos < self.next_check_pos:
            return eventtime + CHECK_TIMEOUT
        self.next_check_pos = epos + self.check_distance
        moved = abs(value - self.start_value) >= self.threshold
        if not moved and self._in_dead_space(self.start_value) \
           and self._in_dead_space(value):
            self.dead_space_count_now += 1
            self.error_count = 0
            failed = self.dead_space_count_now >= self.dead_space_count
        else:
            self.dead_space_count_now = 0
            self.error_count = 0 if moved else self.error_count + 1
            failed = self.error_count >= self.check_count
        if failed:
            logging.info("Filament sensor %s: no filament motion detected"
                         " (value %.4f, start %.4f)",
                         self.runout_helper.name, value, self.start_value)
        self.runout_helper.note_filament_present(eventtime, not failed)
        self.start_value = value
        return eventtime + CHECK_TIMEOUT
    def get_status(self, eventtime):
        status = self.runout_helper.get_status(eventtime)
        status['value'] = self.last_value
        return status

def load_config_prefix(config):
    return J1FilamentSensor(config)
