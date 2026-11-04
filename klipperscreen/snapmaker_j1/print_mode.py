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
#     (mirror) in X.  Backup needs a file with one toolhead too.
#   - The print is moved in X so that its center is at X 80 (duplication),
#     75 (mirror), or 150 when a duplication or mirror file prints with one
#     toolhead.  The mode the file asks for keeps the print where it is.
# Unlike the stock display, the purge line of the start G-code is not
# moved and does not count: the OrcaSlicer J1 profile purges from X 137 to
# 0 (left toolhead), which leaves no room for a model in half the bed.  The
# print gets a copy of the file with SET_GCODE_OFFSET at the first layer
# (";LAYER_CHANGE", ";LAYER:0"), in gcodes/snapmaker_j1/print_mode/; the
# mode itself applies from the start, so both toolheads purge.  A file
# without a layer mark moves as a whole, purge line included (as stock).
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
# The moved copy of the file to print (one at a time)
COPY_DIR = "snapmaker_j1/print_mode"
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
LAYER = re.compile(rb"\n;(?:LAYER_CHANGE|LAYER:0)\b")
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
    """Read a print file: the mode it asks for, the X range of the
    extrusion of the model (from the first layer on) and of the whole file
    (purge line included), where the first layer starts (file offset), the
    toolheads it changes to and the retraction distance of each toolhead
    (None when the file names none).
    """
    info = {"mode": "FULL_CONTROL", "layer_pos": None,
            "range": [None, None], "model_range": [None, None],
            "tools": set(), "retraction": [None, None]}
    header_mode = m605_mode = None
    state = {"prev": None}
    rest = b"\n"
    rest_start = -1     # file offset of rest[0]
    with open(path, "rb") as f:
        while True:
            data = f.read(CHUNK)
            chunk = rest + data
            chunk_start = rest_start
            if data:
                # The last (maybe cut) line goes with the next chunk
                cut = chunk.rfind(b"\n")
                if cut <= 0:
                    rest = chunk
                    continue
                chunk, rest = chunk[:cut], chunk[cut:]
                rest_start = chunk_start + cut
            if info["layer_pos"] is None:
                m = LAYER.search(chunk)
                if m:
                    info["layer_pos"] = chunk_start + m.start() + 1
                    _extrusion(chunk[:m.start()], state, info["range"])
                    # The model does not start where the purge line ended
                    state["prev"] = None
                    model = chunk[m.start():]
                    _extrusion(model, state, info["range"],
                               info["model_range"])
                else:
                    _extrusion(chunk, state, info["range"])
            else:
                _extrusion(chunk, state, info["range"], info["model_range"])
            info["tools"].update(int(t) for t in TOOL.findall(chunk))
            if m605_mode is None:
                m = M605.search(chunk)
                if m:
                    m605_mode = M605_MODES.get(int(m.group(1)))
            header_mode = _comments(info, chunk) or header_mode
            if not data:
                break
    info["mode"] = header_mode or m605_mode or "FULL_CONTROL"
    return info


def _extrusion(chunk, state, *ranges):
    # Widen the [min, max] ranges by the X of all extrusion in chunk
    prev = state["prev"]
    lo = hi = None
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
                if lo is None or px < lo:
                    lo = px
                if hi is None or px > hi:
                    hi = px
        prev = x
    state["prev"] = prev
    if lo is not None:
        for r in ranges:
            r[0] = lo if r[0] is None else min(r[0], lo)
            r[1] = hi if r[1] is None else max(r[1], hi)


def _moved_range(info):
    # What a mode change moves: the model (from the first layer) or, in a
    # file without a layer mark, everything
    if info["layer_pos"] is not None and info["model_range"][0] is not None:
        return info["model_range"]
    return info["range"]


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
        lo, hi = _moved_range(info)
        if lo is None:
            return _("The size of the print could not be read from the"
                     " file.")
        if hi - lo >= MODE_WIDTH[mode]:
            return _("The model is too large for the Duplication or Mirror"
                     " Mode (%.0f mm wide, at most %.0f mm).") % (
                         hi - lo, MODE_WIDTH[mode])
    return None


def x_offset(info, mode):
    """X shift of the print for this mode (0 for the mode of the file)"""
    lo, hi = _moved_range(info)
    if lo is None:
        return 0.
    center = (lo + hi) / 2.
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
    if info is None or mode is None or mode == info["mode"]:
        logging.info("Starting print: %s", filename)
        panel._screen._ws.api.print_start(filename)
        return
    offset = x_offset(info, mode)
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
            copy = make_copy(filename, info["layer_pos"], offset)
        except (IOError, OSError):
            logging.exception("Preparing %s failed", filename)
            copy = None
        GLib.idle_add(done, copy)

    threading.Thread(target=work, daemon=True).start()


def make_copy(filename, layer_pos, offset):
    """Copy of the print file with SET_GCODE_OFFSET X=offset before the
    first layer, in COPY_DIR (replacing the previous one); returns its
    name relative to the gcodes folder"""
    folder = os.path.join(GCODES, COPY_DIR)
    os.makedirs(folder, exist_ok=True)
    src_path = os.path.join(GCODES, filename)
    for old in os.listdir(folder):
        old = os.path.join(folder, old)
        # (unless the file to print is the previous copy itself)
        if not os.path.samefile(old, src_path):
            os.remove(old)
    name = COPY_DIR + "/" + os.path.basename(filename)
    dest = os.path.join(GCODES, name)
    with open(src_path, "rb") as src, open(dest + ".tmp", "wb") as dst:
        left = layer_pos
        while left > 0:
            data = src.read(min(CHUNK, left))
            if not data:
                break
            dst.write(data)
            left -= len(data)
        dst.write(b"SET_GCODE_OFFSET X=%.2f ; moved for the print mode\n"
                  % (offset,))
        while True:
            data = src.read(CHUNK)
            if not data:
                break
            dst.write(data)
    os.rename(dest + ".tmp", dest)
    return name
