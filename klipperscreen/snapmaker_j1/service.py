# Service page of the touch screen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# A button in the action bar of the main menu opens a page for service
# work: a target temperature per heater (kept, 220C for the nozzles by
# default) with ON/OFF and the current temperature, loading and unloading
# once a nozzle is hot, moving the nozzles in for service, homing and
# distributing fresh grease.  The heaters are set with
# SET_HEATER_TEMPERATURE, which does not block Klipper.
import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.keypad import Keypad

from . import settings, style

PANEL = "snapmaker_service"
CONTROL = "snapmaker_service"
TARGETS = "service_targets"
HEATERS = (("extruder", "Left Nozzle", 220, 0),
           ("extruder1", "Right Nozzle", 220, 1),
           ("heater_bed", "Heater Bed", 60, None))
# Load and unload once the nozzle is this close to its target
READY_MARGIN = 3
MIN_EXTRUDE_TEMP = 170
# Symbol of the service page: a wrench (Material Design Icons "wrench",
# Apache License 2.0, as the icons of the KlipperScreen themes)
WRENCH_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
    ' viewBox="0 0 24 24" fill="%s"><path d="M22.7,19L13.6,9.9C14.5,7.6'
    ' 14,4.9 12.1,3C10.1,1 7.1,0.6 4.7,1.7L9,6L6,9L1.6,4.7C0.4,7.1 0.9,10.1'
    ' 2.9,12.1C4.8,14 7.5,14.5 9.8,13.6L18.9,22.7C19.3,23.1 19.9,23.1'
    ' 20.3,22.7L22.6,20.4C23.1,20 23.1,19.3 22.7,19Z"/></svg>')


def _wrench_pixbuf(size):
    loader = GdkPixbuf.PixbufLoader()
    loader.set_size(int(size), int(size))
    loader.write((WRENCH_SVG % (style.BODY,)).encode())
    loader.close()
    return loader.get_pixbuf()


class ServiceButton:
    # The button in the action bar: on the main menu it opens the service
    # page (wrench), on the service page it returns (thermometer)
    def __init__(self, screen):
        self.screen = screen
        base = screen.base_panel
        size = screen.gtk.img_scale * base.abscale
        self.wrench = Gtk.Image.new_from_pixbuf(_wrench_pixbuf(size * 1.2))
        self.temps = screen.gtk.Image("heat-up", size * 1.4, size * 1.4)
        button = screen.gtk.Button("heat-up", scale=base.abscale)
        button.set_no_show_all(True)
        button.hide()
        button.set_always_show_image(True)
        button.connect("clicked", self._clicked)
        base.control[CONTROL] = button
        base.action_bar.add(button)
        base.action_bar.reorder_child(
            button, base.action_bar.get_children().index(
                base.control["home"]) + 1)
        self.button = button
        add_content = base.add_content

        def _add_content(panel):
            add_content(panel)
            self._update(panel)

        base.add_content = _add_content

    def _service_open(self):
        panels = self.screen._cur_panels
        return bool(panels) and panels[-1] == PANEL

    def _update(self, panel):
        panels = self.screen.panels
        if panel is not None and panel is panels.get(PANEL):
            self.button.set_image(self.temps)
            self.button.show()
        elif panel is not None and panel is panels.get("main_menu"):
            self.button.set_image(self.wrench)
            self.button.show()
        else:
            self.button.hide()

    def _clicked(self, widget):
        if self._service_open():
            self.screen._menu_go_back()
        else:
            self.screen.show_panel(PANEL, _("Service"))


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _("Service"))
        self.rows = {}
        self.keypad_heater = None
        self.serviced = False
        targets = settings.get(TARGETS, {})
        self.targets = {heater: targets.get(heater, default)
                        for heater, _name, default, _tool in HEATERS}

        self.grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True,
                             hexpand=True, vexpand=True)
        for row, (heater, name, _default, tool) in enumerate(HEATERS):
            self._heater_row(row, heater, _(name), tool)
        self.buttons = {
            "nozzles": self._gtk.Button("extruder", _("Nozzle Service"),
                                        "color1"),
            "home": self._gtk.Button("home", _("Home All"), "color2"),
            "grease": self._gtk.Button("refresh", _("Distribute Grease"),
                                       "color3"),
        }
        self.buttons["nozzles"].connect("clicked", self._nozzles)
        self.buttons["home"].connect("clicked", self._home)
        self.buttons["grease"].connect("clicked", self._grease)
        # Both nozzles at once, beside the bed (it has no Load and Unload)
        self.both = {
            "load": self._gtk.Button("arrow-down", _("Load Both"), "color3"),
            "unload": self._gtk.Button("arrow-up", _("Unload Both"),
                                       "color2"),
        }
        self.both["load"].connect("clicked", self._filament,
                                  "SNAPMAKER_LOAD_FILAMENT", 2)
        self.both["unload"].connect("clicked", self._filament,
                                    "SNAPMAKER_UNLOAD_FILAMENT", 2)
        self.grid.attach(self.both["load"], 4, 2, 1, 1)
        self.grid.attach(self.both["unload"], 5, 2, 1, 1)
        fine = self._gtk.Button("fine-tune", _("Fine Tuning"), "color4")
        fine.connect("clicked", self._fine_tune)
        off = self._gtk.Button("cool-down", _("All Off"), "color1")
        off.connect("clicked", self._all_off)
        row = len(HEATERS)
        self.grid.attach(self.buttons["nozzles"], 0, row, 1, 1)
        self.grid.attach(self.buttons["home"], 1, row, 1, 1)
        self.grid.attach(self.buttons["grease"], 2, row, 2, 1)
        self.grid.attach(fine, 4, row, 1, 1)
        self.grid.attach(off, 5, row, 1, 1)

        self.keypad = Keypad(screen, self._keypad_ok, self._keypad_close,
                             entry_max=3)
        self.keypad_title = Gtk.Label(hexpand=True)
        self.keypad_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                  spacing=self._gtk.font_size // 2,
                                  halign=Gtk.Align.CENTER, hexpand=True,
                                  vexpand=True)
        self.keypad_box.set_size_request(screen.width // 3, -1)
        self.keypad_box.add(self.keypad_title)
        self.keypad_box.pack_start(self.keypad, True, True, 0)
        self.content.add(self.grid)

    # A heater: name, current temperature, target, ON/OFF and for the
    # nozzles Load and Unload
    def _heater_row(self, row, heater, name, tool):
        # Name and current temperature in one tile, as the heaters of the
        # main menu (icon, color bar); a tap sets the target
        image = ("bed" if tool is None else "extruder-%d" % (tool,))
        size = self._gtk.img_scale * self.bts
        box = Gtk.Box(spacing=self._gtk.font_size // 2)
        box.pack_start(self._gtk.Image(image, size, size), False, False, 0)
        # The name gives way (ellipsized) so the temperature keeps its
        # distance from the right edge
        box.pack_start(Gtk.Label(label=name, xalign=0, hexpand=True,
                                 ellipsize=Pango.EllipsizeMode.END),
                       True, True, 0)
        temp = Gtk.Label(label="-", xalign=1)
        temp.set_margin_end(round(self._gtk.font_size * 1.5))
        box.pack_end(temp, False, False, 0)
        label = Gtk.Button(hexpand=True, vexpand=True)
        label.add(box)
        for css in ("graph_label_" + heater, "graph_label"):
            label.get_style_context().add_class(css)
        label.connect("clicked", self._edit, heater)
        target = self._gtk.Button(None, "", "color4")
        target.connect("clicked", self._edit, heater)
        power = self._gtk.Button(None, _("ON"), "color1")
        power.connect("clicked", self._power, heater)
        self.grid.attach(label, 0, row, 2, 1)
        self.grid.attach(target, 2, row, 1, 1)
        self.grid.attach(power, 3, row, 1, 1)
        widgets = {"temp": temp, "target": target, "power": power}
        if tool is not None:
            load = self._gtk.Button("arrow-down", _("Load"), "color3")
            unload = self._gtk.Button("arrow-up", _("Unload"), "color2")
            load.connect("clicked", self._filament,
                         "SNAPMAKER_LOAD_FILAMENT", tool)
            unload.connect("clicked", self._filament,
                           "SNAPMAKER_UNLOAD_FILAMENT", tool)
            self.grid.attach(load, 4, row, 1, 1)
            self.grid.attach(unload, 5, row, 1, 1)
            widgets["load"] = load
            widgets["unload"] = unload
        self.rows[heater] = widgets
        self._show_target(heater)

    def _show_target(self, heater):
        self.rows[heater]["target"].set_label(
            "%d°C" % (self.targets[heater],))

    def activate(self):
        self._refresh()

    def process_update(self, action, data):
        if action == "notify_status_update":
            self._refresh()

    def _stat(self, heater, name):
        return self._printer.get_stat(heater, name) or 0

    def _refresh(self):
        if self._printer is None:
            return
        ready_all = {}
        for heater, widgets in self.rows.items():
            temp = self._stat(heater, "temperature")
            current = self._stat(heater, "target")
            widgets["temp"].set_label("%.1f°C" % (temp,))
            on = current > 0
            widgets["power"].set_label(_("OFF") if on else _("ON"))
            # A heater that is on: orange frame, as a selected heater
            for key in ("target", "power"):
                context = widgets[key].get_style_context()
                if on:
                    context.add_class("button_active")
                else:
                    context.remove_class("button_active")
            if "load" in widgets:
                ready = (on and current >= MIN_EXTRUDE_TEMP
                         and temp >= current - READY_MARGIN)
                widgets["load"].set_sensitive(ready)
                widgets["unload"].set_sensitive(ready)
                ready_all[heater] = ready
        both = all(ready_all.values())
        self.both["load"].set_sensitive(both)
        self.both["unload"].set_sensitive(both)

    # Target temperatures
    def _max_temp(self, heater):
        section = self._printer.get_config_section(heater) or {}
        try:
            return float(section.get("max_temp", 300))
        except (TypeError, ValueError):
            return 300.

    def _edit(self, widget, heater):
        self.keypad_heater = heater
        name = next(name for h, name, _d, _t in HEATERS if h == heater)
        self.keypad_title.set_label(_(name))
        self.keypad.clear()
        self.content.remove(self.grid)
        self.content.add(self.keypad_box)
        self.content.show_all()

    def _keypad_close(self, widget=None):
        if self.keypad_heater is None:
            return
        self.keypad_heater = None
        self.content.remove(self.keypad_box)
        self.content.add(self.grid)
        self.content.show_all()

    def _keypad_ok(self, value):
        heater = self.keypad_heater
        limit = self._max_temp(heater)
        if not 0 < value <= limit:
            self._screen.show_popup_message(
                _("Temperature must be between 1 and %d°C") % (limit,))
            return
        self.targets[heater] = int(value)
        settings.save(TARGETS, self.targets)
        self._show_target(heater)
        # A heater that is on follows the new target at once
        if self._stat(heater, "target") > 0:
            self._set_target(heater, self.targets[heater])
        self._keypad_close()

    def back(self):
        if self.keypad_heater is not None:
            self._keypad_close()
            return True
        return False

    def _set_target(self, heater, temp):
        self._screen._ws.api.gcode_script(
            "SET_HEATER_TEMPERATURE HEATER=%s TARGET=%d" % (heater, temp))

    def _power(self, widget, heater):
        on = self._stat(heater, "target") > 0
        self._set_target(heater, 0 if on else self.targets[heater])

    # Filament, service, homing, grease
    def _filament(self, widget, macro, tool):
        # At the nozzle service position (moves there unless it is there)
        # TOOL=2: both at once, each at its own target
        heater = "extruder1" if tool == 1 else "extruder"
        self._screen._ws.api.gcode_script(
            "%s TOOL=%d TEMP=%d SERVICE=1" % (macro, tool,
                                              self._stat(heater, "target")))
        self._set_serviced(True)

    def _set_serviced(self, serviced):
        self.serviced = serviced
        self.buttons["nozzles"].set_label(_("Park Nozzles") if serviced
                                          else _("Nozzle Service"))

    def _nozzles(self, widget):
        self._screen._ws.api.gcode_script(
            "SNAPMAKER_NOZZLE_PARK" if self.serviced
            else "SNAPMAKER_NOZZLE_SERVICE")
        self._set_serviced(not self.serviced)

    def _fine_tune(self, widget):
        self._screen.show_panel("fine_tune", _("Fine Tuning"))

    def _all_off(self, widget):
        for heater, _name, _default, _tool in HEATERS:
            self._set_target(heater, 0)

    def _home(self, widget):
        self._screen._ws.api.gcode_script("G28")

    def _grease(self, widget):
        label = Gtk.Label(hexpand=True, vexpand=True,
                          halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                          wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                          justify=Gtk.Justification.CENTER,
                          max_width_chars=48)
        label.set_markup("%s\n\n%s" % (
            GLib.markup_escape_text(
                _("Moves both nozzles, the bed and the Z axis once over"
                  " their travel to spread fresh grease (about a minute)."
                  " Tap again for another run.")),
            GLib.markup_escape_text(
                _("Remove everything from the build plate first."))))
        buttons = [
            {"name": _("Start"), "response": Gtk.ResponseType.OK,
             "style": "dialog-info"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-secondary"},
        ]

        def response(dialog, response_id):
            self._gtk.remove_dialog(dialog)
            if response_id == Gtk.ResponseType.OK:
                self._set_serviced(False)
                self._screen._ws.api.gcode_script(
                    "SNAPMAKER_DISTRIBUTE_GREASE")

        self._gtk.Dialog(_("Distribute Grease"), buttons, label, response)
