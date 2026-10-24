# KlipperScreen add-on for the Snapmaker J1
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import os
from math import pi

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from ks_includes.printer import Printer
from ks_includes.screen_panel import ScreenPanel

from . import calibration, datetime_panel, filament, hostname, pause, style

# Install as KlipperScreen/addons/snapmaker_j1 (enable_addons: True) and
# add a menu entry with "panel: snapmaker_calibration".
PANEL = "snapmaker_calibration"
FILAMENT_PANEL = "snapmaker_filament"
HOSTNAME_PANEL = "snapmaker_hostname"
DATETIME_PANEL = "snapmaker_datetime"
PAUSE_PANEL = "snapmaker_pause"
THEME = "snapmaker-j1"
# Klipper object names that KlipperScreen would show as "Extruder" and
# "Extruder1"; the other devices are named in the printer config
NAMES = {"extruder": "Left Nozzle", "extruder1": "Right Nozzle",
         "filament_sensor_t0": "Left Filament",
         "filament_sensor_t1": "Right Filament"}
# Electronics fan (temperature_fan, hidden elsewhere by its underscore)
BOARD_FAN = "temperature_fan _board_fan"
# KlipperScreen lists only Klipper's own filament sensor types
FILAMENT_SENSOR = "snapmaker_j1_filament_sensor "
# Display backlight (KlipperSnapmakerJ1-os lets the group video switch it)
BACKLIGHT_DIR = "/sys/class/backlight"
BL_POWER_ON, BL_POWER_OFF = "0", "4"


def init(screen):
    # Provide the calibration panel without adding files to KlipperScreen
    load_panel = screen._load_panel

    def _load_panel(panel):
        if panel == PANEL:
            return calibration
        if panel == FILAMENT_PANEL:
            return filament
        if panel == HOSTNAME_PANEL:
            return hostname
        if panel == DATETIME_PANEL:
            return datetime_panel
        if panel == PAUSE_PANEL:
            return pause
        module = load_panel(panel)
        if panel == "job_status":
            _patch_progress_ring(screen, module.Panel)
            _patch_heat_button(module.Panel)
        elif panel == "move":
            _patch_move_options(module.Panel)
        elif panel == "fan":
            _patch_device_label(module.Panel, "add_fan")
            _patch_board_fan(module.Panel)
        elif panel == "pins":
            _patch_device_label(module.Panel, "add_pin")
        return module

    screen._load_panel = _load_panel

    # The calibration test prints run inside the calibration menu, so the
    # automatic switch to the job status (and back to the main menu when
    # the print ends) is suppressed while one of them runs
    screen.snapmaker_calibration_print = False
    state_printing = screen.state_printing
    state_ready = screen.state_ready

    def _state_printing():
        if not screen.snapmaker_calibration_print:
            state_printing()

    def _state_ready(wait=True):
        if not screen.snapmaker_calibration_print:
            state_ready(wait)

    screen.state_printing = _state_printing
    screen.state_ready = _state_ready

    # A print paused for a filament runout or change (M600) opens the
    # stock refill dialog instead of the extrude panel
    state_paused = screen.state_paused

    def _state_paused():
        def got(result, method, params, *args):
            try:
                tool = result["result"]["status"][
                    "gcode_macro _SNAPMAKER_STATE"]["runout_tool"]
            except (KeyError, TypeError):
                tool = -1
            if tool not in (0, 1) or screen.snapmaker_calibration_print:
                state_paused()
                return
            screen.state_printing()
            screen.show_panel(FILAMENT_PANEL, _("Filament"))

        screen._ws.api.query_objects(
            {"gcode_macro _SNAPMAKER_STATE": ["runout_tool"]}, got)

    screen.state_paused = _state_paused

    # The J1 is switched off with its power switch and loses no data when
    # the power is cut (power loss recovery); the shutdown button of the
    # action bar is not needed.  The emergency stop still shows while
    # printing, Klipper restarts are offered on the error screen.
    base_panel = screen.base_panel
    update_action_bar = base_panel.update_action_bar

    def _update_action_bar():
        update_action_bar()
        base_panel.control["shutdown"].set_visible(False)

    base_panel.update_action_bar = _update_action_bar
    _update_action_bar()

    # The stock kernel (3.10) has no MemAvailable, so Moonraker reports the
    # system memory without "used" and the titlebar usage display fails
    # on every update
    process_update = base_panel.process_update

    def _process_update(action, data):
        if action == "notify_proc_stat_update":
            memory = data.get("system_memory") or {}
            if "used" not in memory or not memory.get("total"):
                return
        return process_update(action, data)

    base_panel.process_update = _process_update

    # Device names as on the stock display
    prettify = ScreenPanel.prettify

    def _prettify(name):
        return NAMES.get(name) or prettify(name)

    ScreenPanel.prettify = staticmethod(_prettify)

    # The analog filament sensors in the extrude panel (status and on/off
    # switch; the module stores the switch state)
    get_filament_sensors = Printer.get_filament_sensors
    if not getattr(get_filament_sensors, "snapmaker_j1", False):
        def _get_filament_sensors(self):
            if self.sensors is None:
                get_filament_sensors(self).extend(
                    self.get_config_section_list(FILAMENT_SENSOR))
            return self.sensors

        _get_filament_sensors.snapmaker_j1 = True
        Printer.get_filament_sensors = _get_filament_sensors

    # Dialog choices centered below the message (GTK puts them at the
    # right end)
    make_dialog = screen.gtk.Dialog
    if not getattr(make_dialog, "snapmaker_j1", False):
        def _dialog(*args, **kwargs):
            dialog = make_dialog(*args, **kwargs)
            dialog.get_action_area().set_halign(Gtk.Align.CENTER)
            return dialog

        _dialog.snapmaker_j1 = True
        screen.gtk.Dialog = _dialog

    _patch_screensaver()
    datetime_panel.apply_clock(screen)
    logging.info("Snapmaker J1 add-on: calibration panel '%s'", PANEL)


def _set_backlight(value):
    # Under Wayland KlipperScreen's screen saver only shows a black page;
    # the backlight is switched like DPMS would on X11
    try:
        names = os.listdir(BACKLIGHT_DIR)
    except OSError:
        return
    for name in names:
        try:
            with open(os.path.join(BACKLIGHT_DIR, name, "bl_power"), "w") as f:
                f.write(value)
        except OSError as e:
            logging.info("Backlight %s not switched: %s", name, e)


def _patch_screensaver():
    from ks_includes.widgets.screensaver import ScreenSaver
    if getattr(ScreenSaver.show, "snapmaker_j1", False):
        return
    show, close = ScreenSaver.show, ScreenSaver.close

    def _show(self, *args):
        result = show(self, *args)
        if self.is_showing:
            _set_backlight(BL_POWER_OFF)
        return result

    def _close(self, *args):
        if self.is_showing:
            _set_backlight(BL_POWER_ON)
        return close(self, *args)

    _show.snapmaker_j1 = True
    ScreenSaver.show, ScreenSaver.close = _show, _close


def _patch_progress_ring(screen, panel_class):
    # KlipperScreen draws the print progress ring in fixed colors; with the
    # snapmaker-j1 theme it gets the track and orange gradient of the stock
    # display
    on_draw = panel_class.on_draw
    if getattr(on_draw, "snapmaker_j1", False):
        return

    def _on_draw(self, da, ctx):
        themedir = os.path.normpath(screen.gtk.themedir)
        if os.path.basename(os.path.dirname(themedir)) != THEME:
            return on_draw(self, da, ctx)
        import cairo
        w = da.get_allocated_width()
        h = da.get_allocated_height()
        r = min(w, h) * 0.42
        ctx.set_line_width(self._gtk.font_size * 0.75)
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.translate(w / 2, h / 2)
        ctx.set_source_rgb(*_rgb(style.TRACK))
        ctx.arc(0, 0, r, 0, 2 * pi)
        ctx.stroke()
        if self.progress <= 0:
            return
        gradient = cairo.LinearGradient(-r, 0, r, 0)
        gradient.add_color_stop_rgb(0, *_rgb(style.PRIMARY_START))
        gradient.add_color_stop_rgb(1, *_rgb(style.PRIMARY_END))
        ctx.set_source(gradient)
        ctx.arc(0, 0, r, 3 / 2 * pi, 3 / 2 * pi + (self.progress * 2 * pi))
        ctx.stroke()

    _on_draw.snapmaker_j1 = True
    panel_class.on_draw = _on_draw


def _patch_heat_button(panel_class):
    # A paused print cools down after a while (PAUSE); the print page gets
    # a button that heats it to its print temperatures again, for example
    # before loading filament
    show_buttons = panel_class.show_buttons_for_state
    if getattr(show_buttons, "snapmaker_j1", False):
        return

    def _show_buttons_for_state(self):
        show_buttons(self)
        if self.state != "paused":
            return
        if "snapmaker_heat" not in self.buttons:
            button = self._gtk.Button("heat-up", _("Heat"), "color3")
            button.connect(
                "clicked", lambda widget: self._screen._ws.klippy.gcode_script(
                    "SNAPMAKER_PAUSE_HEAT"))
            self.buttons["snapmaker_heat"] = button
        grid = self.buttons["button_grid"]
        grid.insert_column(1)
        grid.attach(self.buttons["snapmaker_heat"], 1, 0, 1, 1)
        grid.show_all()

    _show_buttons_for_state.snapmaker_j1 = True
    panel_class.show_buttons_for_state = _show_buttons_for_state


def _patch_move_options(panel_class):
    # The axis inversion switches of the move panel only mirror buttons and
    # graphs of KlipperScreen; the J1 menu already shows the directions of
    # the printer (the bed moves in Z), so the switches would only confuse
    add_option = panel_class.add_option
    if getattr(add_option, "snapmaker_j1", False):
        return

    def _add_option(self, boxname, opt_array, opt_name, option):
        if opt_name in ("invert_x", "invert_y", "invert_z"):
            return {}
        return add_option(self, boxname, opt_array, opt_name, option)

    _add_option.snapmaker_j1 = True
    panel_class.add_option = _add_option


def _patch_board_fan(panel_class):
    # The fan panel lists no temperature fans; show the board fan there
    # read only, as the hotend fans (it follows the board temperature)
    load_fans = panel_class.load_fans
    if getattr(load_fans, "snapmaker_j1", False):
        return
    # KlipperScreen calls activate/deactivate only when a panel has them
    activate = getattr(panel_class, "activate", None)
    deactivate = getattr(panel_class, "deactivate", None)

    def _load_fans(self):
        load_fans(self)
        if BOARD_FAN not in self._printer.get_config_section_list(BOARD_FAN):
            return
        name = Gtk.Label(halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
                         hexpand=True, vexpand=True)
        name.set_markup("\n<big><b>%s</b></big>\n" % _("Board Fan"))
        self.snapmaker_board_fan = Gtk.ProgressBar(hexpand=True,
                                                   show_text=True)
        bar = Gtk.Box(spacing=5)
        bar.pack_start(self.snapmaker_board_fan, True, True, 10)
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        row.add(name)
        row.add(bar)
        self.labels["devices"].attach(row, 0, len(self.devices) + 1, 1, 1)
        self.labels["devices"].show_all()

    def _update_board_fan(self):
        def got(result, method, params, *args):
            try:
                fan = result["result"]["status"][BOARD_FAN]
            except (KeyError, TypeError):
                return
            self.snapmaker_board_fan.set_fraction(fan["speed"])
            self.snapmaker_board_fan.set_text(
                "%d%%  (%s %.0f °C)" % (round(fan["speed"] * 100),
                                        _("Board"), fan["temperature"]))

        self._screen._ws.api.query_objects(
            {BOARD_FAN: ["speed", "temperature"]}, got)
        return True

    def _activate(self):
        if activate is not None:
            activate(self)
        if getattr(self, "snapmaker_board_fan", None) is not None:
            _update_board_fan(self)
            self.snapmaker_board_timer = GLib.timeout_add_seconds(
                2, _update_board_fan, self)

    def _deactivate(self):
        timer = getattr(self, "snapmaker_board_timer", None)
        if timer is not None:
            GLib.source_remove(timer)
            self.snapmaker_board_timer = None
        if deactivate is not None:
            deactivate(self)

    _load_fans.snapmaker_j1 = True
    panel_class.load_fans = _load_fans
    panel_class.activate = _activate
    panel_class.deactivate = _deactivate


def _patch_device_label(panel_class, method):
    # The fan and pin panels show the raw object name ("left_part_fan");
    # give them the readable form the other panels use ("Left Part Fan")
    add = getattr(panel_class, method)
    if getattr(add, "snapmaker_j1", False):
        return

    def _add(self, device, *args, **kwargs):
        result = add(self, device, *args, **kwargs)
        raw = device.split(" ", 1)[-1]
        # The new row is not in the panel content yet while it is built
        roots = [self.labels.get("devices"),
                 self.devices.get(device, {}).get("row")]
        for label in (l for r in roots if r is not None for l in _labels(r)):
            if label.get_text().strip() == raw:
                label.set_markup("\n<big><b>%s</b></big>\n"
                                 % GLib.markup_escape_text(
                                     ScreenPanel.prettify(raw)))
        return result

    _add.snapmaker_j1 = True
    setattr(panel_class, method, _add)


def _labels(widget):
    if isinstance(widget, Gtk.Label):
        yield widget
    elif isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from _labels(child)


def _rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255. for i in (0, 2, 4))
