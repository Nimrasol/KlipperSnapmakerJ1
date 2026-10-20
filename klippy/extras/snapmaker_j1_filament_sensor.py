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

# The J1 filament sensor outputs an analog voltage that changes while
# filament moves through it.  After every check_distance of extrusion
# the reading must have changed by at least `threshold`.  Readings
# close to the ends of the sensor range ("dead space") change little
# even with moving filament, so they only report a problem after an
# additional dead_space_distance of extrusion.
class J1FilamentSensor:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.extruder_name = config.get('extruder')
        self.check_distance = config.getfloat('check_distance', 3., above=0.)
        self.threshold = config.getfloat('threshold', 15. / 4096., above=0.)
        self.check_count = config.getint('check_count', 3, minval=1)
        self.dead_space_min = config.getfloat('dead_space_min', 60. / 4096.,
                                              minval=0.)
        self.dead_space_max = config.getfloat('dead_space_max', 4060. / 4096.,
                                              maxval=1.)
        dead_space_distance = config.getfloat('dead_space_distance', 4.,
                                              minval=0.)
        self.dead_space_count = self.check_count + int(
            dead_space_distance / self.check_distance + .5)
        # ADC setup
        ppins = self.printer.lookup_object('pins')
        self.mcu_adc = ppins.setup_pin('adc', config.get('adc_pin'))
        self.mcu_adc.setup_adc_sample(ADC_REPORT_TIME, ADC_SAMPLE_TIME,
                                      ADC_SAMPLE_COUNT)
        self.mcu_adc.setup_adc_callback(self._adc_callback)
        query_adc = self.printer.load_object(config, 'query_adc')
        query_adc.register_adc(config.get_name(), self.mcu_adc)
        self.runout_helper = filament_switch_sensor.RunoutHelper(config)
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
        print_time = self.estimated_print_time(eventtime)
        return self.extruder.find_past_position(print_time)
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
