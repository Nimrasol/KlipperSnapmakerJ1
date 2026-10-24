# Pause standby settings for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# A print paused for longer than the delay turns its nozzles off and keeps
# the bed at the standby temperature (PAUSE in snapmaker-j1-macros.cfg);
# the values are stored by Klipper (save_variables).
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

# Defaults, limits and steps as in SNAPMAKER_SET_PAUSE_STANDBY
BED_DEFAULT, BED_MAX, BED_STEP = 50, 100, 5
DELAY_DEFAULT, DELAY_MIN, DELAY_MAX, DELAY_STEP = 10, 1, 120, 5
VARIABLES = "save_variables"


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _("Pause Standby"))
        self.bed = BED_DEFAULT
        self.delay = DELAY_DEFAULT
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      spacing=self._gtk.font_size, vexpand=True)
        box.set_margin_start(self._gtk.font_size)
        box.set_margin_end(self._gtk.font_size)
        intro = Gtk.Label(
            label=_("A paused print turns its part fans off at once. After "
                    "the delay the nozzles cool down and the bed stays at "
                    "the standby temperature, so the print keeps sticking to "
                    "the plate. Resume and Load Filament heat to the print "
                    "temperatures again."),
            wrap=True, xalign=0, wrap_mode=Pango.WrapMode.WORD_CHAR)
        box.pack_start(intro, False, False, 0)
        self.bed_label = self._row(box, _("Bed standby temperature"),
                                   self._change_bed)
        self.delay_label = self._row(box, _("Cool down after"),
                                     self._change_delay)
        self.content.add(box)
        self._show()

    def _row(self, box, name, callback):
        row = Gtk.Box(spacing=self._gtk.font_size, hexpand=True)
        row.pack_start(Gtk.Label(label=name, xalign=0, hexpand=True),
                       True, True, 0)
        for icon, step in (("decrease", -1), (None, 0), ("increase", 1)):
            if icon is None:
                value = Gtk.Label(width_chars=7)
                row.pack_start(value, False, False, 0)
                continue
            button = self._gtk.Button(icon, None, "color1", scale=.66)
            button.set_vexpand(False)
            button.set_hexpand(False)
            button.connect("clicked", callback, step)
            row.pack_start(button, False, False, 0)
        box.pack_start(row, False, False, 0)
        return value

    def _show(self):
        self.bed_label.set_label("%d °C" % self.bed if self.bed else _("Off"))
        self.delay_label.set_label("%d min" % self.delay)

    def activate(self):
        def got(result, method, params, *args):
            try:
                variables = result["result"]["status"][VARIABLES]["variables"]
            except (KeyError, TypeError):
                return
            self.bed = int(variables.get("snap_j1_pause_bed_temp",
                                         BED_DEFAULT))
            self.delay = int(variables.get("snap_j1_pause_delay",
                                           DELAY_DEFAULT))
            self._show()

        self._screen._ws.api.query_objects({VARIABLES: ["variables"]}, got)

    def _change_bed(self, widget, step):
        self.bed = min(max(self.bed + step * BED_STEP, 0), BED_MAX)
        self._save("BED=%d" % self.bed)

    def _change_delay(self, widget, step):
        # 1, 5, 10, 15 ... minutes
        delay = (self.delay // DELAY_STEP + step) * DELAY_STEP
        if step < 0 and self.delay % DELAY_STEP:
            delay += DELAY_STEP
        self.delay = min(max(delay, DELAY_MIN), DELAY_MAX)
        self._save("DELAY=%d" % self.delay)

    def _save(self, value):
        self._show()
        self._screen._ws.klippy.gcode_script(
            "SNAPMAKER_SET_PAUSE_STANDBY " + value)
