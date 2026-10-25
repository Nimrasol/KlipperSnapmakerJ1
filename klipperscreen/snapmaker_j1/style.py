# Look of the Snapmaker J1 display application for the calibration menu
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

# Palette and dimensions of the stock application (res/values/colors.xml,
# styles.xml and the j1 layouts); sizes are given in Android dp
PAGE = "#1a1c28"
CARD_TOP = "#3d3f4d"
CARD_BOTTOM = "#2d2f40"
TRACK = "#191b27"
TITLE = "#f7f8fa"
BODY = "#c4c5cc"
BODY_PRIMARY = "#9b9ca6"
EXPLAIN = "#737480"
DISABLED = "#595a66"
PRIMARY = "#ff8a00"
PRIMARY_START = "#ffab00"
PRIMARY_END = "#f56a00"
PRESSED_START = "#ff5500"
PRESSED_END = "#ff9500"
WARNING = "#ff6b00"
SUCCESS = "#18b65b"
ERROR = "#fc5244"
HEATING = "#ffd600"
FONT = "Roboto, 'Noto Sans', 'DejaVu Sans', sans-serif"

# The stock pages are 432dp high (480dp screen below the 48dp toolbar);
# they are scaled to the content area KlipperScreen leaves to a panel
DP_HEIGHT = 432.

CSS = """
.snapj1, .snapj1 * {
    font-family: %(font)s;
}
.snapj1 {
    background-color: %(page)s;
}
.snapj1 label {
    color: %(body)s;
    font-size: %(body2)s;
}
.snapj1 .snap-title {
    color: %(title)s;
    font-size: %(title2)s;
    font-weight: 500;
}
.snapj1 .snap-progress {
    color: %(explain)s;
}
.snapj1 .snap-warning {
    color: %(warning)s;
}
.snapj1 .snap-value {
    color: %(title)s;
    font-size: %(body1)s;
}
.snapj1 .snap-card {
    background-color: %(card_bottom)s;
    background-image: linear-gradient(to bottom, %(card_top)s,
                                      %(card_bottom)s);
    border-radius: %(r12)s;
}
.snapj1 .snap-page-card {
    border-radius: %(r22)s;
}

/* Left section list with the white indicator of the selected entry */
.snapj1 button.snap-section,
.snapj1 button.snap-section:hover,
.snapj1 button.snap-section:active {
    background: none;
    border: none;
    box-shadow: none;
    margin: 0;
    padding: 0 0 0 %(d16)s;
    min-height: %(d56)s;
}
/* Line above the optional entries */
.snapj1 button.snap-section.snap-separated {
    border-top: 1px solid %(explain)s;
    border-radius: 0;
}
.snapj1 button.snap-section label {
    color: %(title)s;
    font-size: %(body2)s;
}
.snapj1 button.snap-section.selected label {
    font-weight: 600;
}
.snapj1 .snap-indicator {
    min-width: %(d3)s;
    min-height: %(d36)s;
    border-radius: %(d3)s;
    background-color: transparent;
}
.snapj1 button.snap-section.selected .snap-indicator {
    background-color: %(title)s;
}

.snapj1 button:disabled {
    opacity: 1;
}

/* Primary button: horizontal orange gradient, fully rounded */
.snapj1 button.snap-primary {
    background-color: %(primary)s;
    background-image: linear-gradient(to right, %(primary_start)s,
                                      %(primary_end)s);
    border: none;
    box-shadow: none;
    border-radius: %(d48)s;
    min-width: %(d140)s;
    min-height: %(d48)s;
    margin: 0;
    padding: 0 %(d16)s;
}
.snapj1 button.snap-primary:active {
    background-image: linear-gradient(to right, %(pressed_start)s,
                                      %(pressed_end)s);
}
.snapj1 button.snap-primary:disabled {
    background-image: none;
    background-color: %(disabled)s;
}
.snapj1 button.snap-primary label {
    color: %(title)s;
    font-size: %(body1)s;
}

/* Secondary button: white outline */
.snapj1 button.snap-secondary {
    background: none;
    border: %(d2)s solid %(title)s;
    box-shadow: none;
    border-radius: %(d48)s;
    min-width: %(d140)s;
    min-height: %(d44)s;
    margin: 0;
    padding: 0 %(d16)s;
}
.snapj1 button.snap-secondary.snap-small {
    min-width: %(d56)s;
    padding: 0 %(d6)s;
}
.snapj1 button.snap-secondary:active {
    border-color: %(body)s;
}
.snapj1 button.snap-secondary:active label {
    color: %(body)s;
}
.snapj1 button.snap-secondary:disabled {
    border-color: %(disabled)s;
}
.snapj1 button.snap-secondary label {
    color: %(title)s;
    font-size: %(body1)s;
}
.snapj1 button.snap-secondary:disabled label {
    color: %(disabled)s;
}

/* Assist mode switch: dark track, orange or grey thumb */
.snapj1 switch {
    background-color: %(track)s;
    background-image: none;
    border: none;
    border-radius: %(d16)s;
    min-height: %(d28)s;
    font-size: 0;
    color: transparent;
}
.snapj1 switch:checked {
    background-color: %(track)s;
}
.snapj1 switch image {
    color: transparent;
    -gtk-icon-source: none;
}
.snapj1 switch slider {
    background-color: %(body_primary)s;
    background-image: none;
    border: none;
    box-shadow: none;
    border-radius: 50%%;
    min-width: %(d24)s;
    min-height: %(d24)s;
    margin: %(d2)s;
}
.snapj1 switch:checked slider {
    background-color: %(primary)s;
}
.snapj1 .snap-assist {
    color: %(primary)s;
    font-size: %(body2)s;
}

/* Check boxes, radio buttons and the print progress */
.snapj1 checkbutton label,
.snapj1 radiobutton label {
    color: %(title)s;
    font-size: %(body1)s;
}
.snapj1 checkbutton,
.snapj1 radiobutton {
    padding: %(d6)s 0;
}
.snapj1 checkbutton label,
.snapj1 radiobutton label {
    margin-left: %(d12)s;
}
.snapj1 check,
.snapj1 radio {
    background-color: %(track)s;
    background-image: none;
    border: %(d2)s solid %(body_primary)s;
    min-width: %(d24)s;
    min-height: %(d24)s;
    color: %(title)s;
    -gtk-icon-source: none;
}
.snapj1 check {
    border-radius: %(d4)s;
}
.snapj1 radio {
    border-radius: 50%%;
}
.snapj1 check:checked,
.snapj1 radio:checked {
    background-color: %(primary)s;
    border-color: %(primary)s;
}
.snapj1 check:checked {
    -gtk-icon-source: -gtk-icontheme("object-select-symbolic");
}
.snapj1 progressbar trough {
    background-color: %(track)s;
    border: none;
    border-radius: %(d6)s;
    min-height: %(d12)s;
}
.snapj1 progressbar progress {
    background-color: %(primary)s;
    background-image: linear-gradient(to right, %(primary_start)s,
                                      %(primary_end)s);
    border: none;
    border-radius: %(d6)s;
    min-height: %(d12)s;
}
.snapj1 progressbar text {
    color: %(title)s;
    font-size: %(body2)s;
}
"""

_installed = []


def dp(screen, value):
    return value * screen.gtk.content_height / DP_HEIGHT


def install(screen):
    """Add the stylesheet once; it stays above every KlipperScreen theme."""
    if _installed:
        return
    def px(value):
        return "%dpx" % round(dp(screen, value))
    values = {
        "font": FONT, "page": PAGE, "card_top": CARD_TOP,
        "card_bottom": CARD_BOTTOM, "track": TRACK, "title": TITLE,
        "body": BODY, "body_primary": BODY_PRIMARY, "explain": EXPLAIN,
        "disabled": DISABLED, "primary": PRIMARY,
        "primary_start": PRIMARY_START, "primary_end": PRIMARY_END,
        "pressed_start": PRESSED_START, "pressed_end": PRESSED_END,
        "warning": WARNING,
        "body1": px(18), "body2": px(16), "title2": px(20),
        "r12": px(12), "r22": px(22.5),
    }
    for size in (2, 3, 4, 6, 12, 16, 24, 28, 36, 44, 48, 56, 140):
        values["d%d" % size] = px(size)
    provider = Gtk.CssProvider()
    provider.load_from_data((CSS % values).encode())
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10)
    _installed.append(provider)
