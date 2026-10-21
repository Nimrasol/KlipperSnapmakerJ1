# Snapmaker J1 filament runout and change dialog for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.screen_panel import ScreenPanel

from . import calibration
from . import style as S

# The stock display (PrintA400Fragment, shared by the J1) asks for new
# filament when a sensor reports a runout, heats the nozzle, lets the user
# insert the filament while the extruder feeds it (100mm at 240mm/min)
# and continues the print once the user sees filament at the nozzle.
LOAD_LENGTH = 100
LOAD_SPEED = 240
UNLOAD_LENGTH = 80
# Small stock icons keep their size instead of filling the picture area
ICON_SIZES = {"icon_tips_success_64x64": 80}
STATE = "gcode_macro _SNAPMAKER_STATE"


class Panel(calibration.Panel):
    def __init__(self, screen, title):
        # The page helpers of the calibration panel, without its menu
        ScreenPanel.__init__(self, screen, title or _("Filament"))
        S.install(screen)
        self.tool = 0
        self.reason = "runout"
        self.synced = False
        self.page = None
        self.pending = False
        self.step_ready = True
        self.step_widgets = {}
        self.page_after_error = "start"

    def activate(self):
        def got(result, method, params, *args):
            try:
                state = result["result"]["status"][STATE]
            except (KeyError, TypeError):
                state = {}
            tool = state.get("runout_tool", -1)
            self.tool = tool if tool in (0, 1) else self._active_tool()
            self.reason = state.get("runout_reason") or "change"
            self.synced = state.get("print_mode") in ("DUPLICATION", "MIRROR")
            self._show("start")

        self._screen._ws.api.query_objects(
            {STATE: ["runout_tool", "runout_reason", "print_mode"]}, got)

    def _active_tool(self):
        extruder = self._printer.get_stat("toolhead", "extruder")
        return 1 if extruder == "extruder1" else 0

    def _extruder(self):
        return "extruder1" if self.tool == 1 else "extruder"

    def _tool_name(self):
        return _("Nozzle R") if self.tool == 1 else _("Nozzle L")

    # Pages
    def _show(self, page, message=None):
        self.page = page
        self._clear()
        self.step_widgets = {}
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True,
                       vexpand=True)
        self._styled(card, "snap-card", "snap-page-card")
        card.set_margin_top(self._dp(8))
        for side in ("start", "end", "bottom"):
            getattr(card, "set_margin_" + side)(self._dp(16))
        image, title, text, buttons = getattr(self, "_page_" + page)()
        body = Gtk.Box(spacing=self._dp(16), vexpand=True)
        for side in ("top", "start", "end"):
            getattr(body, "set_margin_" + side)(self._dp(16))
        size = ICON_SIZES.get(image)
        if size is None:
            picture = self._image(image, self._dp(160), self._dp(180))
        else:
            picture = self._image(image, self._dp(size), self._dp(size))
            picture.set_margin_start(self._dp((160 - size) // 2))
            picture.set_margin_end(self._dp((160 - size) // 2))
        picture.set_valign(Gtk.Align.START)
        body.pack_start(picture, False, False, 0)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                        spacing=self._dp(12), hexpand=True)
        right.pack_start(self._label(title, "snap-title", hexpand=True),
                         False, False, 0)
        label = self._body_label(text, hexpand=True)
        self.step_widgets["text"] = label
        right.pack_start(label, False, False, 0)
        if page == "start" and self.synced:
            right.pack_start(self._tool_selector(), False, False, 0)
        status = self._label(message or "", "snap-warning")
        self.step_widgets["status"] = status
        right.pack_start(status, False, False, 0)
        body.pack_start(right, True, True, 0)
        card.pack_start(body, True, True, 0)
        bar = self._bottom_bar()
        for label, kind, callback in buttons:
            button = self._button(label, kind)
            button.connect("clicked", callback)
            if kind == "primary":
                bar.pack_end(self._bar_button(button, "end"), False, False, 0)
            else:
                bar.pack_start(self._bar_button(button, "start"), False,
                               False, 0)
        self.step_widgets["buttons"] = bar
        card.pack_start(bar, False, False, 0)
        self.content.add(self._root(card))
        self.content.show_all()
        self._update_temperature()

    def _page_start(self):
        if self.reason == "runout":
            title = _("Filament Runout Recovery")
            text = (_("%s is not loaded.\nTo continue printing, tap Load"
                      " Filament.") % self._tool_name())
        else:
            title = _("Change Filament")
            text = (_("Unload the filament of %s, then load the new"
                      " filament.") % self._tool_name())
        return ("pic_warning_filament_runout_120x120", title, text, [
            (_("Cancel"), "secondary", self._cancel),
            (_("Unload"), "secondary", self._unload),
            (_("Load Filament"), "primary", self._to_insert)])

    def _page_insert(self):
        if self.reason == "runout":
            title = _("Pull out Filament")
            text = _("Manually pull out the filament and insert it into the"
                     " filament guide tube again until you can feel the"
                     " filament is gripped and being pulled in.")
        else:
            title = _("Insert Filament")
            text = _("Manually insert the new filament into the filament"
                     " guide tube until you can feel the filament is gripped"
                     " and being pulled in.")
        text += "\n\n" + _("Tap Load to heat the nozzle and feed the"
                           " filament.")
        return ("pic_calibration_j1_z_offset_load_filament", title, text, [
            (_("Cancel"), "secondary", self._cancel),
            (_("Load"), "primary", self._load)])

    def _page_busy(self):
        return ("pic_calibration_j1_z_offset_load_filament",
                self.step_widgets.get("busy_title", _("Load Filament")),
                "", [])

    def _page_loaded(self):
        return ("icon_tips_success_64x64", _("Filament Loaded"),
                _("Observe if any filament is coming out of the nozzle. If"
                  " yes, then the filament is loaded and you can tap Continue"
                  " Printing to resume the job. If not, tap Load Filament to"
                  " load again."), [
            (_("Load Filament"), "secondary", self._load),
            (_("Continue Printing"), "primary", self._resume)])

    def _tool_selector(self):
        # Duplication and mirror mode print with both toolheads
        box = Gtk.Box(spacing=self._dp(12), homogeneous=True,
                      halign=Gtk.Align.START)
        for tool, name in ((0, _("Nozzle L")), (1, _("Nozzle R"))):
            button = self._button(name, "primary" if tool == self.tool
                                  else "secondary", small=True)
            button.connect("clicked", self._select_tool, tool)
            box.pack_start(button, True, True, 0)
        return box

    def _select_tool(self, widget, tool):
        self.tool = tool
        self._show("start")

    # Actions
    def _run(self, script, title, done):
        logging.info("Filament: %s", script)
        self.step_widgets["busy_title"] = title
        self.pending = True
        self._show("busy")

        def finished(result, method, params, *args):
            self.pending = False
            if "error" in result:
                message = result["error"].get("message",
                                              str(result["error"]))
                logging.error("Filament step failed: %s", message)
                self._show(self.page_after_error, message)
                return
            done()

        self._screen._ws.api.gcode_script(script, finished)

    def _to_insert(self, widget):
        self._show("insert")

    def _unload(self, widget):
        self.page_after_error = "start"
        self._run("UNLOAD_FILAMENT TOOL=%d LENGTH=%d"
                  % (self.tool, UNLOAD_LENGTH), _("Unload Filament"),
                  lambda: self._show("insert"))

    def _load(self, widget):
        self.page_after_error = "insert"
        self._run("LOAD_FILAMENT TOOL=%d LENGTH=%d SPEED=%d"
                  % (self.tool, LOAD_LENGTH, LOAD_SPEED), _("Load Filament"),
                  lambda: self._show("loaded"))

    def _resume(self, widget):
        # RESUME primes and checks the filament sensor; the job status
        # panel replaces this one when the print continues
        self.page_after_error = "loaded"
        self._run("RESUME", _("Continue Printing"), lambda: None)

    def _cancel(self, widget):
        self._screen._menu_go_back()

    def back(self):
        if self.pending:
            return True
        return False

    # Status
    def process_update(self, action, data):
        if action == "notify_status_update" and self.page == "busy":
            self._update_temperature()

    def _update_temperature(self):
        if self.page != "busy":
            return
        extruder = self._extruder()
        temp = self._printer.get_stat(extruder, "temperature") or 0.
        target = self._printer.get_stat(extruder, "target") or 0.
        if target and temp < target - 3:
            text = _("Heating the nozzle...") + "\n%.0f / %.0f°C" % (
                temp, target)
        elif self.step_widgets.get("busy_title") == _("Unload Filament"):
            text = _("Unloading the filament, this takes a few seconds...")
        else:
            text = _("Extruding filament, this takes a few seconds...")
        self.step_widgets["text"].set_label(text)
