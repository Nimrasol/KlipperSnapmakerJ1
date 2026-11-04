# Print mode choice and file checks before a print, for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# The print dialog offers the four IDEX modes; the checks and the moving
# of the print are in scripts/snapmaker_j1_print_file.py (shared with
# SNAPMAKER_PRINT_MODE of Klipper, the same choice for the web interface).
import importlib.util
import logging
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

_spec = importlib.util.spec_from_file_location(
    "snapmaker_j1_print_file",
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..",
                 "scripts", "snapmaker_j1_print_file.py"))
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)
pf._t = _
GCODES = pf.GCODES
MODES = pf.MODES


MODE_NAMES = {
    "FULL_CONTROL": "IDEX", "BACKUP": "Backup",
    "DUPLICATION": "Duplication", "MIRROR": "Mirror",
}


def patch_gcodes(screen, panel_class):
    # The print dialog with the mode buttons; the rest as KlipperScreen's
    # own (panels/gcodes.py)
    if getattr(panel_class.confirm_print, "snapmaker_j1", False):
        return

    def _confirm_print(self, widget, filename):
        action = _("Print")
        buttons = [
            {"name": _("Delete"), "response": Gtk.ResponseType.REJECT,
             "style": "dialog-error"},
            {"name": action, "response": Gtk.ResponseType.OK,
             "style": "dialog-primary"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-secondary"},
        ]
        label = Gtk.Label(hexpand=True, vexpand=True, lines=2, wrap=True,
                          wrap_mode=Pango.WrapMode.WORD_CHAR,
                          ellipsize=Pango.EllipsizeMode.END)
        label.set_markup(f"<b>{GLib.markup_escape_text(filename)}</b>")
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                           vexpand=True)
        main_box.pack_start(label, False, False, 0)

        # Print mode: the file's, until the user picks another
        state = {"info": None, "quick": None, "mode": None, "buttons": {}}
        mode_box = Gtk.Box(spacing=5, hexpand=True)
        for mode in MODES:
            b = self._gtk.Button(None, _(MODE_NAMES[mode]), "color3")
            b.set_vexpand(False)
            b.set_sensitive(False)
            b.connect("clicked", _pick_mode, self, state, mode)
            state["buttons"][mode] = b
            mode_box.pack_start(b, True, True, 0)
        main_box.pack_start(mode_box, False, False, 5)
        # Reading a large file takes some seconds
        status = Gtk.Label(label=_("Checking the file..."))
        main_box.pack_start(status, False, False, 0)

        inside_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                             vexpand=True)
        width = self._screen.width * 0.5
        height = (self._screen.height - self._gtk.dialog_buttons_height
                  - self._gtk.font_size * 9)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                           vexpand=True)
        fileinfo_data = self._screen.files.get_file_info(filename)
        fileinfo_text = self.get_file_info_extended(fileinfo_data)
        fileinfo = Gtk.Label(label=fileinfo_text, use_markup=True,
                             ellipsize=Pango.EllipsizeMode.END)
        info_box.pack_start(fileinfo, True, True, 0)
        if "job_id" in fileinfo_data:
            self._screen._ws.api.get_single_job_history(
                fileinfo_data["job_id"], self.set_last_duration, fileinfo,
                fileinfo_text)
        inside_box.pack_start(info_box, True, True, 0)
        main_box.pack_start(inside_box, True, True, 0)
        self._gtk.Dialog(f"{action} {filename}", buttons, main_box,
                         _response, self, filename, state)
        self.load_image_async(
            filename, width, height,
            callback=lambda p: self._add_print_image(p, inside_box,
                                                     filename))

        def checked(quick):
            state["quick"] = quick
            return False

        def analyzed(info):
            state["info"] = info
            status.set_text("" if info else _("The file could not be read."))
            _show_mode(state, info["mode"] if info else "FULL_CONTROL")
            for b in state["buttons"].values():
                b.set_sensitive(info is not None)
            return False

        def work():
            path = os.path.join(GCODES, filename)
            try:
                GLib.idle_add(checked, pf.quick_check(path))
                info = pf.analyze(path)
            except (IOError, OSError, ValueError):
                logging.exception("Reading %s failed", filename)
                info = None
            GLib.idle_add(analyzed, info)

        threading.Thread(target=work, daemon=True).start()

    _confirm_print.snapmaker_j1 = True
    panel_class.confirm_print = _confirm_print


def _show_mode(state, mode):
    state["mode"] = mode
    for m, b in state["buttons"].items():
        ctx = b.get_style_context()
        if m == mode:
            ctx.add_class("button_active")
        else:
            ctx.remove_class("button_active")


def _pick_mode(widget, panel, state, mode):
    info = state["info"]
    if info is None:
        return
    reason = pf.check_mode(info, mode)
    if reason:
        panel._screen.show_popup_message(reason, 2)
        return
    _show_mode(state, mode)


def _response(dialog, response_id, panel, filename, state):
    panel._gtk.remove_dialog(dialog)
    if response_id == Gtk.ResponseType.REJECT:
        panel.confirm_delete_file(None, f"gcodes/{filename}")
        return
    if response_id != Gtk.ResponseType.OK:
        return
    checked = state["info"] or state["quick"]
    if checked is not None and pf.retraction_too_long(checked):
        _ask_retraction(panel, filename, state)
        return
    _start(panel, filename, state)


def _ask_retraction(panel, filename, state):
    buttons = [
        {"name": _("Print Anyway"), "response": Gtk.ResponseType.OK,
         "style": "dialog-warning"},
        {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
         "style": "dialog-secondary"},
    ]
    label = Gtk.Label(
        label=_("The retraction distance set for this print exceeds the"
                " recommended range (0-2 mm), which might cause nozzle"
                " clogging during printing. Adjust it in the slicer before"
                " printing."),
        wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
    label.set_halign(Gtk.Align.CENTER)
    label.set_valign(Gtk.Align.CENTER)

    def response(dialog, response_id):
        panel._gtk.remove_dialog(dialog)
        if response_id == Gtk.ResponseType.OK:
            _start(panel, filename, state)

    panel._gtk.Dialog(_("Inappropriate Retraction Distance"), buttons,
                      label, response)


def _start(panel, filename, state):
    info, mode = state["info"], state["mode"]
    if info is None or mode is None or mode == info["mode"]:
        logging.info("Starting print: %s", filename)
        panel._screen._ws.api.print_start(filename)
        return
    offset = pf.x_offset(info, mode)
    if not offset or info["layer_pos"] is None:
        # Moved as a whole (or not at all)
        logging.info("Starting print: %s in mode %s, X offset %.2f",
                     filename, mode, offset)
        panel._screen._ws.api.gcode_script(
            'SDCARD_PRINT_FILE FILENAME="%s" MODE=%s X_OFFSET=%.2f'
            % (filename, mode, offset))
        return
    # The model moves from the first layer on: a copy of the file with
    # the offset there (takes a moment for a large file)
    panel._screen.show_popup_message(_("Preparing the print..."), 1)

    def done(copy):
        if copy is None:
            panel._screen.show_popup_message(
                _("The print could not be prepared."))
            return False
        logging.info("Starting print: %s in mode %s, X offset %.2f from"
                     " the first layer (%s)", filename, mode, offset, copy)
        panel._screen._ws.api.gcode_script(
            'SDCARD_PRINT_FILE FILENAME="%s" MODE=%s X_OFFSET=0'
            % (copy, mode))
        return False

    def work():
        try:
            copy = pf.make_copy(filename, info["layer_pos"], offset)
        except (IOError, OSError):
            logging.exception("Preparing %s failed", filename)
            copy = None
        GLib.idle_add(done, copy)

    threading.Thread(target=work, daemon=True).start()


