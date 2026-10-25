# Light of the printer for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# The case light in four steps, dimmed after a time without touch as the
# screen saver blanks the display, and the display settings of
# KlipperScreen (the add-on removes them from the settings panel).
import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

from . import settings

CASE_LIGHT = "case_light"
PIN = "output_pin " + CASE_LIGHT
# The chosen step, which Klipper sets again at startup (_SNAPMAKER_INIT)
VARIABLE = "snap_j1_case_light"
# Steps of the case light (PWM duty)
LEVELS = (0., .02, .5, 1.)
# Minutes without touch before the case light dims, 0 for never
DIM_DELAYS = (0, 1, 2, 5, 15, 30, 60, 120)
DIM_DELAY_DEFAULT, DIM_LEVEL_DEFAULT = 0, 1
# Options of KlipperScreen for the display, shown here instead of in the
# settings panel
DISPLAY_OPTIONS = ("screen_blanking", "screen_blanking_printing",
                   "screensaver_wake_delay", "use_dpms")
# Seconds between attempts while Klipper does not take the command, and
# after the last slider movement before it is sent
RETRY_DELAY = 2
SLIDER_DELAY = 300


def level_names():
    return (_("Off"), _("Low"), _("Medium"), _("Max"))


def nearest_level(value):
    return min(range(len(LEVELS)), key=lambda i: abs(LEVELS[i] - value))


class CaseLight:
    # Sets the case light, repeating the command until Klipper takes it,
    # and dims it after the delay without touch
    def __init__(self, screen):
        self.screen = screen
        self.pending = None
        self.chosen = None
        self.sending = False
        self.dimmed = None
        self.dim_timer = None
        self.listener = None
        # Every touch, also the one that ends the screen saver
        self.gesture = Gtk.GestureMultiPress.new(screen)
        self.gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.gesture.connect("pressed", self._touched)
        self.activity()

    def available(self):
        printer = self.screen.printer
        return printer is not None and PIN in printer.get_output_pins()

    def level(self):
        if self.pending is not None:
            return self.pending
        return nearest_level(float(self.screen.printer.get_pin_value(PIN)))

    def busy(self):
        return self.pending is not None

    def set_level(self, level):
        # A step chosen on the screen, not dimmed
        self.dimmed = None
        self.chosen = level
        self._set(level)

    def _set(self, level):
        self.pending = level
        self._notify()
        if not self.sending:
            self._send()

    def _send(self):
        if self.pending is None:
            self.sending = False
            return False
        self.sending = True
        level = self.pending
        script = "SET_PIN PIN=%s VALUE=%s" % (CASE_LIGHT, LEVELS[level])
        if self.chosen == level:
            script += "\nSAVE_VARIABLE VARIABLE=%s VALUE=%s" % (
                VARIABLE, LEVELS[level])

        def done(result, method, params, *args):
            if not isinstance(result, dict) or "error" in result:
                logging.info("Case light not set yet: %s", result)
                GLib.timeout_add_seconds(RETRY_DELAY, self._send)
                return
            if self.chosen == level:
                self.chosen = None
            if self.pending == level:
                self.pending = None
            self._send()
            self._notify()

        sent = self.screen._ws.api.gcode_script(script, done)
        if not sent:
            GLib.timeout_add_seconds(RETRY_DELAY, self._send)
        return False

    def _notify(self):
        if self.listener is not None:
            self.listener()

    def _touched(self, *args):
        self.activity()

    def activity(self):
        # Back to the light before dimming, the delay starts again
        if self.dim_timer is not None:
            GLib.source_remove(self.dim_timer)
            self.dim_timer = None
        if self.dimmed is not None:
            before, dimmed = self.dimmed
            self.dimmed = None
            # Unless it was set elsewhere in the meantime
            if self.available() and self.level() == dimmed:
                self._set(before)
        delay = settings.get("light_dim_delay", DIM_DELAY_DEFAULT)
        if delay:
            self.dim_timer = GLib.timeout_add_seconds(delay * 60, self._dim)

    def _dim(self):
        self.dim_timer = None
        if self.available():
            level = self.level()
            dimmed = settings.get("light_dim_level", DIM_LEVEL_DEFAULT)
            if dimmed < level:
                self._set(dimmed)
                self.dimmed = (level, dimmed)
        return False


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _("Light"))
        self.light = screen.snapmaker_case_light
        self.slider_timer = None
        self.display = {}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if self.light.available():
            box.add(self._heading(_("Case Light")))
            box.add(self._light_row())
            names = level_names()
            box.add(self._dropdown(
                _("Dim after"), _("Time without touch before the case light "
                                  "dims"),
                [(_("Never") if m == 0 else "%d min" % m, m)
                 for m in DIM_DELAYS],
                settings.get("light_dim_delay", DIM_DELAY_DEFAULT),
                self._dim_delay_changed))
            box.add(self._dropdown(
                _("Dim to"), None, [(names[i], i) for i in range(len(LEVELS))],
                settings.get("light_dim_level", DIM_LEVEL_DEFAULT),
                self._dim_level_changed))
        box.add(self._heading(_("Display")))
        self.labels["display"] = Gtk.Grid()
        box.add(self.labels["display"])
        for option in self._config.get_configurable_options():
            name = list(option)[0]
            if name in DISPLAY_OPTIONS:
                option = dict(option[name])
                if name == "use_dpms":
                    # Without "Not all screens support this": the J1 does
                    option["tooltip"] = _("Enable screen power management")
                self.add_option("display", self.display, name, option)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(box)
        self.content.add(scroll)

    def _heading(self, text):
        label = Gtk.Label(xalign=0, margin_top=self._gtk.font_size / 2)
        label.set_markup("<big><b>%s</b></big>" % text)
        return label

    def _row(self, name, tooltip=None, vertical=False):
        label = Gtk.Label(hexpand=True, halign=Gtk.Align.START, xalign=0,
                          wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        label.set_markup("<big><b>%s</b></big>" % name)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                         valign=Gtk.Align.CENTER)
        labels.add(label)
        if tooltip:
            labels.add(Gtk.Label(label=tooltip, halign=Gtk.Align.START,
                                 xalign=0, wrap=True,
                                 wrap_mode=Pango.WrapMode.WORD_CHAR))
        row = Gtk.Box(spacing=5, hexpand=True, valign=Gtk.Align.CENTER)
        if vertical:
            row.set_orientation(Gtk.Orientation.VERTICAL)
        row.get_style_context().add_class("frame-item")
        row.add(labels)
        return row

    def _light_row(self):
        row = self._row(_("Brightness"), vertical=True)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0,
                                              len(LEVELS) - 1, 1)
        self.scale.set_digits(0)
        self.scale.set_round_digits(0)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.set_has_origin(True)
        self.scale.get_style_context().add_class("fan_slider")
        for i, name in enumerate(level_names()):
            self.scale.add_mark(i, Gtk.PositionType.BOTTOM, name)
        self.scale.set_value(self.light.level())
        self.scale_handler = self.scale.connect("value-changed",
                                                self._slider_moved)
        # GTK ignores taps on the ends of the bar ("Off", "Max"); a tap
        # anywhere on it selects the nearest step
        self.scale_tap = Gtk.GestureMultiPress.new(self.scale)
        self.scale_tap.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.scale_tap.connect("released", self._slider_tapped)
        # Busy while Klipper has not taken the new value yet
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(self._gtk.font_size * 2, -1)
        line = Gtk.Box(spacing=5)
        line.pack_start(self.scale, True, True, 0)
        line.pack_start(self.spinner, False, False, 0)
        row.add(line)
        return row

    def _dropdown(self, name, tooltip, items, active, callback):
        row = self._row(name, tooltip)
        dropdown = Gtk.ComboBoxText(valign=Gtk.Align.CENTER)
        for i, (text, value) in enumerate(items):
            dropdown.append(str(value), text)
            if value == active:
                dropdown.set_active(i)
        dropdown.connect("changed", callback)
        row.add(dropdown)
        return row

    def _dim_delay_changed(self, dropdown):
        settings.save("light_dim_delay", int(dropdown.get_active_id()))
        self.light.activity()

    def _dim_level_changed(self, dropdown):
        settings.save("light_dim_level", int(dropdown.get_active_id()))

    def _slider_tapped(self, gesture, n_press, x, y):
        trough = self.scale.get_range_rect()
        start, end = self.scale.get_slider_range()
        knob = end - start
        width = trough.width - knob
        if width <= 0:
            return
        position = (x - trough.x - knob / 2) / width
        level = round(min(max(position, 0), 1) * (len(LEVELS) - 1))
        self.scale.set_value(level)

    def _slider_moved(self, scale):
        if self.slider_timer is not None:
            GLib.source_remove(self.slider_timer)
        self.slider_timer = GLib.timeout_add(SLIDER_DELAY, self._slider_set)

    def _slider_set(self):
        self.slider_timer = None
        level = int(round(self.scale.get_value()))
        if self.light.busy() or level != self.light.level():
            self.light.set_level(level)
        return False

    def _show(self):
        if not self.light.available():
            return
        # The slider keeps a new value until Klipper has taken it
        if self.slider_timer is None:
            self.scale.handler_block(self.scale_handler)
            self.scale.set_value(self.light.level())
            self.scale.handler_unblock(self.scale_handler)
        if self.light.busy():
            self.spinner.start()
        else:
            self.spinner.stop()

    def activate(self):
        self.light.listener = self._show
        self._show()

    def deactivate(self):
        self.light.listener = None

    def process_update(self, action, data):
        if action == "notify_status_update" and PIN in data:
            self._show()
