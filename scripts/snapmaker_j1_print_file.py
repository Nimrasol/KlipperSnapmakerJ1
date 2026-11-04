# Print file checks for the IDEX print modes of the Snapmaker J1
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Used by the print dialog of the touch screen (klipperscreen/snapmaker_j1/
# print_mode.py) and by SNAPMAKER_PRINT_MODE of Klipper (klippy/extras/
# snapmaker_j1.py); both load it by its path.  Plain Python, no Klipper or
# GTK imports.
#
# As the stock display (Snapmaker-J1-Screen-App, BrowseFileDetailViewModel):
# every file can print in the four IDEX modes; a mode other than the
# file's moves the print where the mode needs it, and a retraction distance
# above 2 mm gets a warning.
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
import os
import re

# Translation of the reasons check_mode() gives (KlipperScreen sets it)
_t = str

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
    "IDEX Full Control": "FULL_CONTROL", "IDEX Backup": "BACKUP",
    "IDEX Duplication": "DUPLICATION", "IDEX Mirror": "MIRROR",
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
# OrcaSlicer: the retraction of the printer profile, and that of the
# filament profiles ("nil" where they keep the printer's), which wins
COMMENT = re.compile(
    rb"\n;[ \t]*(Extruder Mode|Extruder [01] Retraction Distance)[ \t]*:"
    rb"([^\n]*)|\n;[ \t]*(filament_retraction_length|retraction_length)"
    rb"[ \t]*=([^\n]*)")


def _comments(info, chunk):
    # Mode header and retraction distances; returns the header mode
    mode = None
    for key, value, orca_key, orca in COMMENT.findall(chunk):
        if orca_key:
            # Kept apart, merged by _retraction()
            field = ("filament_retraction"
                     if orca_key == b"filament_retraction_length"
                     else "orca_retraction")
            info[field] = [_float(v.decode())
                           for v in orca.split(b",")[:2]]
        elif key == b"Extruder Mode":
            mode = HEADER_MODES.get(value.decode().strip()) or mode
        else:
            info["retraction"][int(key[9:10])] = _float(value.decode())
    return mode


def _retraction(info):
    # The retraction of each toolhead: the filament profile's, else the
    # printer profile's (OrcaSlicer), else the header's (Luban)
    printer = info.pop("orca_retraction", None) or []
    filament = info.pop("filament_retraction", None) or []
    for i in range(2):
        for values in (filament, printer):
            if i < len(values) and values[i] is not None:
                info["retraction"][i] = values[i]
                break


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
    _retraction(info)
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
    _retraction(info)
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
            return _t("The Backup Mode is disabled for dual-extrusion"
                     " models.")
        return _t("The Duplication or Mirror Mode is disabled for"
                 " dual-extrusion models.")
    if mode in DUAL_MODES and mode != info["mode"]:
        lo, hi = _moved_range(info)
        if lo is None:
            return _t("The size of the print could not be read from the"
                     " file.")
        if hi - lo >= MODE_WIDTH[mode]:
            return _t("The model is too large for the Duplication or Mirror"
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


def make_copy(filename, layer_pos, offset, gcodes=None):
    """Copy of the print file with SET_GCODE_OFFSET X=offset before the
    first layer, in COPY_DIR (replacing the previous one); returns its
    name relative to the gcodes folder"""
    gcodes = gcodes or GCODES
    folder = os.path.join(gcodes, COPY_DIR)
    os.makedirs(folder, exist_ok=True)
    src_path = os.path.join(gcodes, filename)
    for old in os.listdir(folder):
        old = os.path.join(folder, old)
        # Files only (Moonraker keeps its thumbnails in .thumbs), not the
        # file to print if that is the previous copy itself
        if os.path.isfile(old) and not os.path.samefile(old, src_path):
            os.remove(old)
    name = COPY_DIR + "/" + os.path.basename(filename)
    dest = os.path.join(gcodes, name)
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
    os.replace(dest + ".tmp", dest)
    return name


SUMMARY = re.compile(
    rb"\n;[ \t]*(?:estimated printing time \(normal mode\)[ \t]*=|"
    rb"Estimated Print Time[ \t]*:)[ \t]*([^\n]*)"
    rb"|\n;[ \t]*filament used \[mm\][ \t]*=[ \t]*([0-9.]+)")


def summary(path):
    """Print time and filament length of a file for a list entry, from
    the slicer comments at its start and end ("" when there are none)"""
    with open(path, "rb") as f:
        data = b"\n" + f.read(HEAD_SIZE)
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size > HEAD_SIZE:
            f.seek(max(HEAD_SIZE, size - TAIL_SIZE))
            data += b"\n" + f.read()
    time = length = None
    for t, mm in SUMMARY.findall(data):
        if t and time is None:
            t = t.decode("utf-8", "replace").strip()
            # Luban writes seconds
            if re.fullmatch(r"[0-9.]+", t):
                s = int(float(t))
                t = ("%dh %dm" % (s // 3600, s // 60 % 60) if s >= 3600
                     else "%dm %ds" % (s // 60, s % 60))
            time = t
        if mm and length is None:
            length = float(mm)
    parts = []
    if time:
        parts.append("Print time: " + time)
    if length:
        # As in the file list of Mainsail
        parts.append("Filament: %.2f m" % (length / 1000.) if length >= 1000.
                     else "Filament: %.0f mm" % length)
    return ", ".join(parts)


def short_name(name, width=30):
    """A file name that fits a button of the dialog"""
    base = os.path.basename(name)
    for ext in (".gcode", ".gco", ".g"):
        if base.lower().endswith(ext):
            base = base[:-len(ext)]
            break
    if len(base) > width:
        keep = (width - 1) // 2
        base = base[:keep] + "\u2026" + base[-(width - 1 - keep):]
    return base
