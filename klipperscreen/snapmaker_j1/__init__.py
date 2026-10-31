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

from ks_includes.KlippyGtk import find_widget
from ks_includes.printer import Printer
from ks_includes.screen_panel import ScreenPanel

from . import (calibration, chooser, datetime_panel, filament, hostname,
               light, pause, stock, style)

# Install as KlipperScreen/addons/snapmaker_j1 (enable_addons: True) and
# add a menu entry with "panel: snapmaker_calibration".
PANEL = "snapmaker_calibration"
FILAMENT_PANEL = "snapmaker_filament"
HOSTNAME_PANEL = "snapmaker_hostname"
DATETIME_PANEL = "snapmaker_datetime"
PAUSE_PANEL = "snapmaker_pause"
LIGHT_PANEL = "snapmaker_light"
STOCK_PANEL = "snapmaker_stock"
# Order of the menus (KlipperScreen shows them in the order of the config
# sections, its defaults first); entries not named here follow
MENU_ORDER = {
    # The print first, then preparing it, the setup and More last
    ("__main", ""): ("print", "temperature", "extrude", "move",
                     "snapmaker_calibration", "more"),
    # Printing, settings of the printer, tools and maintenance
    ("__main", "more"): ("fine_tune", "limits", "fan", "snapmaker_pause",
                         "snapmaker_light", "snapmaker_datetime",
                         "snapmaker_network", "settings",
                         "macros", "console", "updater", "system"),
}
THEME = "snapmaker-j1"
# Klipper object names that KlipperScreen would show as "Extruder" and
# "Extruder1"; the other devices are named in the printer config
NAMES = {"extruder": "Left Nozzle", "extruder1": "Right Nozzle",
         "filament_sensor_t0": "Left Filament",
         "filament_sensor_t1": "Right Filament"}
# Print mode of the J1 (macro state) and its names on the print page
STATE_MACRO = "gcode_macro _SNAPMAKER_STATE"
PRINT_MODES = {"FULL_CONTROL": "IDEX", "DUPLICATION": "Duplication",
               "MIRROR": "Mirror", "BACKUP": "Backup"}
# Electronics fan (temperature_fan, hidden elsewhere by its underscore)
BOARD_FAN = "temperature_fan _board_fan"
# KlipperScreen lists only Klipper's own filament sensor types
FILAMENT_SENSOR = "snapmaker_j1_filament_sensor "
# Display backlight (KlipperSnapmakerJ1-os lets the group video switch it)
BACKLIGHT_DIR = "/sys/class/backlight"
BL_POWER_ON, BL_POWER_OFF = "0", "4"
# Recovery state of an interrupted print
POWER_LOSS = "snapmaker_j1_power_loss"
# Klipper's own lines around a shutdown reason, not shown on the screen
SHUTDOWN_LINES = ("MCU shutdown", "Printer is shutdown",
                  "Error configuring printer")
STOPPED_STATES = ("shutdown", "error")
SHUTDOWN_HINT = "Once the underlying issue is corrected"


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
        if panel == LIGHT_PANEL:
            return light
        if panel == STOCK_PANEL:
            return stock
        module = load_panel(panel)
        if panel == "job_status":
            _patch_progress_ring(screen, module.Panel)
            _patch_job_status(module.Panel)
        elif panel == "move":
            _patch_move_options(module.Panel)
        elif panel == "fan":
            _patch_device_label(module.Panel, "add_fan")
            _patch_board_fan(module.Panel)
        elif panel == "pins":
            _patch_device_label(module.Panel, "add_pin")
        elif panel == "settings":
            _patch_settings_options(module.Panel)
        elif panel == "system":
            _patch_system(screen, module.Panel)
        elif panel == "extrude":
            _patch_extrude(module.Panel)
        return module

    screen._load_panel = _load_panel

    get_menu_items = screen._config.get_menu_items

    def _get_menu_items(menu="__main", subsection=""):
        items = get_menu_items(menu, subsection)
        order = MENU_ORDER.get((menu, subsection))
        if order is None:
            return items

        def rank(item):
            # The keys of a submenu start with its path ("more fan")
            key = next(iter(item)).split()[-1]
            return order.index(key) if key in order else len(order)

        return sorted(items, key=rank)

    screen._config.get_menu_items = _get_menu_items

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
        screen.snapmaker_case_light.klipper_ready()
        if not screen.snapmaker_calibration_print:
            state_ready(wait)
            _offer_power_loss_resume(screen)

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

    # A shutdown or error shows its reason and one restart (a
    # FIRMWARE_RESTART, which also reloads the config) instead of
    # Klipper's instructions
    def _stopped(state_handler):
        def _state():
            state_handler()
            panel = screen.panels.get("splash_screen")
            if panel is not None:
                _shutdown_page(screen, panel)
        return _state

    screen.state_shutdown = _stopped(screen.state_shutdown)
    screen.state_error = _stopped(screen.state_error)

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
    # The emergency stop at the top of the action bar, away from the pause
    # button at the bottom of the print page
    base_panel.action_bar.reorder_child(base_panel.control["estop"], 0)
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

    # A pulled hotend leaves its temperature sensor open (several hundred
    # degrees, above max_temp): the temperature shows as N/A
    update_temp = ScreenPanel.update_temp
    if not getattr(update_temp, "snapmaker_j1", False):
        def _update_temp(self, dev, temp, target, power, *args, **kwargs):
            update_temp(self, dev, temp, target, power, *args, **kwargs)
            if not _temp_invalid(self._printer, dev, temp):
                return
            widget = self.labels.get(dev)
            if widget is None and dev in self.devices:
                widget = self.devices[dev]["temp"]
            if widget is not None:
                find_widget(widget, Gtk.Label).set_text(_("N/A"))

        _update_temp.snapmaker_j1 = True
        ScreenPanel.update_temp = _update_temp

    process_memory = base_panel.process_update

    def _process_titlebar(action, data):
        result = process_memory(action, data)
        if action == "notify_status_update" and screen.printer is not None:
            for dev, label in base_panel.titlebar_labels.items():
                if _temp_invalid(screen.printer, dev,
                                 screen.printer.get_stat(dev, "temperature")):
                    label.set_label(_("N/A"))
        return result

    base_panel.process_update = _process_titlebar

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

    # Drop-downs of the settings open a touch friendly choice
    add_option = ScreenPanel.add_option
    if not getattr(add_option, "snapmaker_j1", False):
        def _add_option(self, boxname, opt_array, opt_name, option):
            setting = add_option(self, boxname, opt_array, opt_name, option)
            widget = (setting or {}).get(opt_name)
            if isinstance(widget, Gtk.ComboBoxText):
                chooser.attach(screen, widget, option["name"])
            return setting

        _add_option.snapmaker_j1 = True
        ScreenPanel.add_option = _add_option

    # Dialog choices centered below the message (GTK puts them at the
    # right end).  KlipperScreen gives two buttons a third of the width
    # each and lets more fill the row, which centered shrinks them to
    # their labels: these get an equal share of the width as well
    make_dialog = screen.gtk.Dialog
    if not getattr(make_dialog, "snapmaker_j1", False):
        def _dialog(*args, **kwargs):
            dialog = make_dialog(*args, **kwargs)
            area = dialog.get_action_area()
            area.set_halign(Gtk.Align.CENTER)
            buttons = area.get_children()
            for button in buttons:
                width, height = button.get_size_request()
                if width < 0:
                    button.set_size_request(
                        int(screen.gtk.width / (len(buttons) + 1)), height)
            return dialog

        _dialog.snapmaker_j1 = True
        screen.gtk.Dialog = _dialog

    _patch_screensaver(screen)
    # A restart of KlipperScreen with the screen saver showing leaves the
    # backlight off
    _set_backlight(BL_POWER_ON)
    datetime_panel.apply_clock(screen)
    screen.snapmaker_case_light = light.CaseLight(screen)
    logging.info("Snapmaker J1 add-on: calibration panel '%s'", PANEL)


def _temp_invalid(printer, dev, temp):
    if not temp or printer is None:
        return False
    section = printer.get_config_section(dev) or {}
    try:
        return temp > float(section.get("max_temp"))
    except (TypeError, ValueError):
        return False


def _shutdown_page(screen, panel):
    if not getattr(panel, "snapmaker_shutdown", False):
        panel.snapmaker_shutdown = True
        update_text = panel.update_text
        show_restart_buttons = panel.show_restart_buttons
        restart = screen.gtk.Button("refresh", _("Restart"), "color1")
        restart.connect("clicked", panel.firmware_restart)

        def _update_text(text):
            panel.labels["text"].set_use_markup(False)
            update_text(text)

        def _show_restart_buttons():
            if (screen.printer is None
                    or screen.printer.state not in STOPPED_STATES):
                show_restart_buttons()
                return
            panel.clear_action_bar()
            panel.labels["actions"].add(restart)
            panel.labels["actions"].add(panel.labels["menu"])
            panel.labels["actions"].show_all()

        panel.update_text = _update_text
        panel.show_restart_buttons = _show_restart_buttons
    msg = screen.printer.get_stat("webhooks", "state_message") or ""
    lines = []
    for line in msg.strip().splitlines():
        if line.startswith(SHUTDOWN_HINT):
            break
        if line.strip() not in SHUTDOWN_LINES:
            lines.append(line)
    reason = "\n".join(lines).strip() or msg.strip()
    panel.labels["text"].set_markup("<big><b>%s</b></big>\n\n%s\n\n%s" % (
        _("Printer stopped"), GLib.markup_escape_text(reason),
        _("Tap Restart once the cause is fixed.")))
    panel.show_restart_buttons()


def _offer_power_loss_resume(screen):
    # As the stock display: after a mains failure (or a failed print) the
    # interrupted print is offered for resuming once Klipper is ready
    if getattr(screen, "snapmaker_power_loss_dialog", None) is not None:
        return

    def got(result, method, params, *args):
        try:
            status = result["result"]["status"]
            state = status[POWER_LOSS]
            printing = status["print_stats"]["state"]
        except (KeyError, TypeError):
            return
        if (not state.get("pending") or printing in ("printing", "paused")
                or getattr(screen, "snapmaker_power_loss_dialog", None)):
            return
        name = os.path.basename(state.get("file_path") or "")
        label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        label.set_markup(
            "%s\n\n<b>%s</b>\n\n%s" % (
                _("A print was interrupted."),
                GLib.markup_escape_text(name),
                _("Resume it? The nozzles heat up and the printer homes"
                  " before the print continues; check that the print is"
                  " still on the plate.")))
        buttons = [
            {"name": _("Resume"), "response": Gtk.ResponseType.OK,
             "style": "dialog-info"},
            {"name": _("Later"), "response": Gtk.ResponseType.CLOSE,
             "style": "dialog-secondary"},
            {"name": _("Discard"), "response": Gtk.ResponseType.REJECT,
             "style": "dialog-error"},
        ]
        screen.snapmaker_power_loss_dialog = screen.gtk.Dialog(
            _("Resume Print"), buttons, label, response)

    def response(dialog, response_id):
        screen.gtk.remove_dialog(dialog)
        # Asked once per start of the screen: the state stays stored while
        # a resumed print heats up, and after "Later"
        screen.snapmaker_power_loss_dialog = False
        if response_id == Gtk.ResponseType.OK:
            screen._ws.api.gcode_script("SNAPMAKER_POWER_LOSS_RESUME")
        elif response_id == Gtk.ResponseType.REJECT:
            screen._ws.api.gcode_script("SNAPMAKER_POWER_LOSS_CLEAR")

    screen._ws.api.query_objects(
        {POWER_LOSS: ["pending", "file_path"], "print_stats": ["state"]}, got)


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


def _patch_screensaver(screen):
    # The screen saver hides the pages and puts a black page below them;
    # panels that call show_all() while it is showing (the print status
    # does at every tool change) bring the pages back on top.  With the
    # backlight off they stay invisible, a touch reaches them instead of
    # the screen saver and the backlight stays off: hide them again
    show_all = screen.show_all
    if not getattr(show_all, "snapmaker_j1", False):
        def _show_all(*args):
            show_all(*args)
            blackbox = screen.screensaver.blackbox
            if blackbox is not None:
                for child in screen.overlay.get_children():
                    if child is not blackbox:
                        child.hide()

        _show_all.snapmaker_j1 = True
        screen.show_all = _show_all

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


def _patch_job_status(panel_class):
    # Print page: the part fans of both toolheads in full (KlipperScreen
    # cuts the fan line to 12 characters, "R:100%" became "R:10") and the
    # print mode next to the elapsed time
    create_status_grid = panel_class.create_status_grid
    if getattr(create_status_grid, "snapmaker_j1", False):
        return
    process_update = panel_class.process_update
    activate = getattr(panel_class, "activate", None)
    deactivate = getattr(panel_class, "deactivate", None)

    def _create_status_grid(self, widget=None):
        create_status_grid(self, widget)
        info = self.status_grid
        elapsed = self.buttons["elapsed"]
        info.remove(elapsed)
        mode = self._gtk.Button("toolchanger", "-", None, self.bts,
                                Gtk.PositionType.LEFT, 1)
        mode.set_halign(Gtk.Align.START)
        self.buttons["snapmaker_mode"] = mode
        row = Gtk.Grid(column_homogeneous=True)
        row.attach(elapsed, 0, 0, 3, 1)
        row.attach(mode, 2, 0, 2, 1)
        info.attach(row, 0, 3, 1, 1)

    def _process_update(self, action, data):
        result = process_update(self, action, data)
        if action == "notify_status_update" and self.fans:
            self.buttons["fan"].set_label("  ".join(
                "%s %d%%" % (fan["name"].rstrip(":"),
                             round(self._printer.get_fan_speed(name) * 100))
                for name, fan in self.fans.items()))
        return result

    def _update_mode(self):
        def got(result, method, params, *args):
            try:
                state = result["result"]["status"][STATE_MACRO]
            except (KeyError, TypeError):
                return
            mode = state.get("print_mode", "")
            label = PRINT_MODES.get(mode, mode.replace("_", " ").title())
            if mode == "BACKUP" and state.get("backup_swapped"):
                label = _("Backup, right")
            button = self.buttons.get("snapmaker_mode")
            if button is not None:
                button.set_label(label)

        self._screen._ws.api.query_objects(
            {STATE_MACRO: ["print_mode", "backup_swapped"]}, got)
        return True

    def _activate(self):
        if activate is not None:
            activate(self)
        _update_mode(self)
        if getattr(self, "snapmaker_mode_timer", None) is None:
            self.snapmaker_mode_timer = GLib.timeout_add_seconds(
                3, _update_mode, self)

    def _deactivate(self):
        timer = getattr(self, "snapmaker_mode_timer", None)
        if timer is not None:
            GLib.source_remove(timer)
            self.snapmaker_mode_timer = None
        if deactivate is not None:
            deactivate(self)

    _create_status_grid.snapmaker_j1 = True
    panel_class.create_status_grid = _create_status_grid
    panel_class.process_update = _process_update
    panel_class.activate = _activate
    panel_class.deactivate = _deactivate


def _patch_move_options(panel_class):
    # The axis inversion switches of the move panel only mirror buttons and
    # graphs of KlipperScreen; the J1 menu already shows the directions of
    # the printer (the bed moves in Z, invert_z is set in
    # snapmaker_j1.conf), so the switches would only confuse
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


def _patch_extrude(panel_class):
    # A parked nozzle presses the filament into its silicone wiper; the
    # extrude and retract buttons move it off first, as load and unload do
    extrude = panel_class.extrude
    if getattr(extrude, "snapmaker_j1", False):
        return

    def _extrude(self, widget, direction):
        extruder = self._printer.get_stat("toolhead", "extruder")
        self._screen._ws.api.gcode_script(
            "_SNAPMAKER_FILAMENT_POSITION TOOL=%d"
            % (1 if extruder == "extruder1" else 0))
        return extrude(self, widget, direction)

    # Its own temperature labels: N/A as in the other panels
    update_temp = panel_class.update_temp

    def _update_temp(self, extruder, temp, target, power):
        update_temp(self, extruder, temp, target, power)
        if _temp_invalid(self._printer, extruder, temp):
            find_widget(self.labels[extruder], Gtk.Label).set_text(_("N/A"))

    _extrude.snapmaker_j1 = True
    panel_class.extrude = _extrude
    panel_class.update_temp = _update_temp


def _patch_settings_options(panel_class):
    # The display settings are in the light panel
    add_option = panel_class.add_option
    if getattr(add_option, "snapmaker_j1", False):
        return

    def _add_option(self, boxname, opt_array, opt_name, option):
        if boxname == "settings" and opt_name in light.DISPLAY_OPTIONS:
            return {}
        return add_option(self, boxname, opt_array, opt_name, option)

    _add_option.snapmaker_j1 = True
    panel_class.add_option = _add_option


def _patch_system(screen, panel_class):
    # Back to the stock firmware is a fallback: a small button at the end
    # of the system information, below everything else
    create_layout = panel_class.create_layout
    if getattr(create_layout, "snapmaker_j1", False):
        return

    def _create_layout(self):
        create_layout(self)
        button = self._gtk.Button("warning", _("Stock Firmware"), None,
                                  self.bts, Gtk.PositionType.LEFT, 1)
        button.set_halign(Gtk.Align.START)
        button.set_vexpand(False)
        button.connect("clicked", lambda widget: screen.show_panel(
            STOCK_PANEL, _("Stock Firmware")))
        self.grid.attach(button, 0, self.current_row, 2, 1)
        self.current_row += 1

    _create_layout.snapmaker_j1 = True
    panel_class.create_layout = _create_layout


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
