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

from ks_includes.screen_panel import ScreenPanel

from . import calibration, style

# Install as KlipperScreen/addons/snapmaker_j1 (enable_addons: True) and
# add a menu entry with "panel: snapmaker_calibration".
PANEL = "snapmaker_calibration"
THEME = "snapmaker-j1"
# Klipper object names that KlipperScreen would show as "Extruder" and
# "Extruder1"; the other devices are named in the printer config
NAMES = {"extruder": "Left Nozzle", "extruder1": "Right Nozzle"}


def init(screen):
    # Provide the calibration panel without adding files to KlipperScreen
    load_panel = screen._load_panel

    def _load_panel(panel):
        if panel == PANEL:
            return calibration
        module = load_panel(panel)
        if panel == "job_status":
            _patch_progress_ring(screen, module.Panel)
        elif panel == "fan":
            _patch_device_label(module.Panel, "add_fan")
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

    # Device names as on the stock display
    prettify = ScreenPanel.prettify

    def _prettify(name):
        return NAMES.get(name) or prettify(name)

    ScreenPanel.prettify = staticmethod(_prettify)
    logging.info("Snapmaker J1 add-on: calibration panel '%s'", PANEL)


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
