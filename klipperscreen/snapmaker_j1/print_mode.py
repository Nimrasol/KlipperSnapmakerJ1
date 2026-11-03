# Print mode choice and file checks before a print, for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# As the stock display (Snapmaker-J1-Screen-App, BrowseFileDetailViewModel):
# the print dialog offers the four IDEX modes for every file and moves the
# print to where the chosen mode needs it, and it warns about a retraction
# distance above 2 mm.
#   - Duplication and mirror need a file that prints with one toolhead and
#     fits half the bed: narrower than 160 mm (duplication) or 150 mm
#     (mirror) in X, the purge line included.  Backup needs a file with
#     one toolhead too.
#   - The print is moved in X so that its center is at X 80 (duplication),
#     75 (mirror), or 150 when a duplication or mirror file prints with one
#     toolhead.  The mode the file asks for keeps the print where it is.
# The printer side is SDCARD_PRINT_FILE MODE= X_OFFSET=
# (snapmaker-j1-macros.cfg).
import logging
import os
import re
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

GCODES = os.path.expanduser("~/printer_data/gcodes")
MODES = ("FULL_CONTROL", "BACKUP", "DUPLICATION", "MIRROR")
DUAL_MODES = ("DUPLICATION", "MIRROR")
# Widest print (X range) and its center for the duplication and mirror mode
MODE_WIDTH = {"DUPLICATION": 160., "MIRROR": 150.}
MODE_CENTER = {"DUPLICATION": 80., "MIRROR": 75.}
SINGLE_CENTER = 150.
MAX_RETRACTION = 2.
# ";Extruder Mode:" of the J1 slicer profiles (Luban) and M605 S<n> of the
# OrcaSlicer profiles
HEADER_MODES = {
    "Default": "FULL_CONTROL", "Normal": "FULL_CONTROL",
    "IDEX Full Control": "FULL_CONTROL", "IDEX Backup": "BACKUP", "IDEX Duplication": "DUPLICATION",
    "IDEX Mirror": "MIRROR",
}
M605_MODES = {0: "FULL_CONTROL", 1: "FULL_CONTROL", 2: "DUPLICATION",
              3: "MIRROR", 4: "BACKUP"}


def _float(text):
    try:
        return float(text.strip().split()[0])
    except (ValueError, IndexError):
        return None


# A print file has a million lines and the display a slow CPU: the file
# is searched in chunks with regular expressions (anchored at "\n", much
# faster than "^" with re.M) instead of parsed line by line.  Extrusion
# is a move with X and a positive E (relative and absolute extrusion
# alike); it starts where the move before it ended.
CHUNK = 4 << 20
HEAD_SIZE = 512 << 10
TAIL_SIZE = 128 << 10
MOVE = re.compile(rb"\nG[01][ \t][^\n;]*?X(-?[0-9]*\.?[0-9]+)([^\n;]*)")
TOOL = re.compile(rb"\nT([01])\b")
M605 = re.compile(rb"\nM605[ \t][^\n;]*?S([0-9])")
COMMENT = re.compile(
    rb"\n;[ \t]*(Extruder Mode|Extruder [01] Retraction Distance)[ \t]*:"
    rb"([^\n]*)|\n;[ \t]*retraction_length[ \t]*=([^\n]*)")


def _comments(info, chunk):
    # Mode header and retraction distances; returns the header mode
    mode = None
    for key, value, orca in COMMENT.findall(chunk):
        if orca:
            for i, v in enumerate(orca.split(b",")[:2]):
                info["retraction"][i] = _float(v.decode())
        elif key == b"Extruder Mode":
            mode = HEADER_MODES.get(value.decode().strip()) or mode
        else:
            info["retraction"][int(key[9:10])] = _float(value.decode())
    return mode


def quick_check(path):
    """The retraction distances from the file header and end (OrcaSlicer
    writes its settings there), at once - the full analyze() takes some
    seconds"""
    info = {"retraction": [None, None]}
    with open(path, "rb") as f:
        head = b"\n" + f.read(HEAD_SIZE)
        f.seek(0, os.SEEK_END)
        size = f.tell()
        tail = b""
        if size > HEAD_SIZE:
            f.seek(max(HEAD_SIZE, size - TAIL_SIZE))
            tail = b"\n" + f.read()
    _comments(info, head)
    _comments(info, tail)
    return info


def analyze(path):
    """Read a print file: the mode it asks for, the X range of all
    extrusion (purge line included), the toolheads it changes to and the
    retraction distance of each toolhead (None when the file names none).
    """
    info = {"mode": "FULL_CONTROL", "min_x": None, "max_x": None,
            "tools": set(), "retraction": [None, None]}
    header_mode = m605_mode = None
    min_x = max_x = prev = None
    rest = b"\n"
    with open(path, "rb") as f:
        while True:
            data = f.read(CHUNK)
            chunk = rest + data
            if data:
                # The last (maybe cut) line goes with the next chunk
                cut = chunk.rfind(b"\n")
                if cut <= 0:
                    rest = chunk
                    continue
                chunk, rest = chunk[:cut], chunk[cut:]
            for x, tail in MOVE.findall(chunk):
                try:
                    x = float(x)
                except ValueError:
                    continue
                e = tail.find(b"E")
                if e >= 0 and tail[e + 1:e + 2] not in (b"-", b""):
                    for px in (prev, x):
                        if px is None:
                            continue
                        if min_x is None or px < min_x:
                            min_x = px
                        if max_x is None or px > max_x:
                            max_x = px
                prev = x
            info["tools"].update(int(t) for t in TOOL.findall(chunk))
            if m605_mode is None:
                m = M605.search(chunk)
                if m:
                    m605_mode = M605_MODES.get(int(m.group(1)))
            header_mode = _comments(info, chunk) or header_mode
            if not data:
                break
    info["mode"] = header_mode or m605_mode or "FULL_CONTROL"
    info["min_x"], info["max_x"] = min_x, max_x
    return info


def check_mode(info, mode):
    """None if the file can print in this mode, else the reason"""
    if mode == "FULL_CONTROL":
        return None
    if len(info["tools"]) > 1:
        if mode == "BACKUP":
            return _("The Backup Mode is disabled for dual-extrusion"
                     " models.")
        return _("The Duplication or Mirror Mode is disabled for"
                 " dual-extrusion models.")
    if mode in DUAL_MODES and mode != info["mode"]:
        if info["min_x"] is None:
            return _("The size of the print could not be read from the"
                     " file.")
        if info["max_x"] - info["min_x"] >= MODE_WIDTH[mode]:
            return _("The printing area (including the purge line) of the"
                     " model is too large for the Duplication or Mirror"
                     " Mode.")
    return None


def x_offset(info, mode):
    """X shift of the print for this mode (0 for the mode of the file)"""
    if info["min_x"] is None:
        return 0.
    center = (info["min_x"] + info["max_x"]) / 2.
    file_dual = info["mode"] in DUAL_MODES
    if mode in DUAL_MODES:
        if file_dual:
            return 0.
        return round(MODE_CENTER[mode] - center, 2)
    if file_dual:
        return round(SINGLE_CENTER - center, 2)
    return 0.


def retraction_too_long(info):
    return any(r is not None and r > MAX_RETRACTION
               for r in info["retraction"])


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
                GLib.idle_add(checked, quick_check(path))
                info = analyze(path)
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
    reason = check_mode(info, mode)
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
    if checked is not None and retraction_too_long(checked):
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
    if info is not None and mode is not None and mode != info["mode"]:
        offset = x_offset(info, mode)
        logging.info("Starting print: %s in mode %s, X offset %.2f",
                     filename, mode, offset)
        panel._screen._ws.api.gcode_script(
            'SDCARD_PRINT_FILE FILENAME="%s" MODE=%s X_OFFSET=%.2f'
            % (filename, mode, offset))
    else:
        logging.info("Starting print: %s", filename)
        panel._screen._ws.api.print_start(filename)
