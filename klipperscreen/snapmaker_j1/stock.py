# Return to the Snapmaker stock firmware, for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# The work is done by scripts/snapmaker_j1_stock.py: as a systemd unit of
# its own, because it stops KlipperScreen; it shows its progress on the
# console of the display.
import json
import logging
import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                      "scripts", "snapmaker_j1_stock.py")
PYTHON = "/home/pi/klippy-env/bin/python"
UNIT = "snapmaker-j1-stock"
BUSY_STATES = ("printing", "paused")


def run_tool(*args, timeout=60):
    return subprocess.run(["sudo", "-n", PYTHON, os.path.realpath(SCRIPT)]
                          + list(args), capture_output=True, text=True,
                          timeout=timeout)


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _("Stock Firmware"))
        self.package = None
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                       spacing=self._gtk.font_size, vexpand=True)
        # The texts scroll, the buttons stay on the page
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      spacing=self._gtk.font_size)
        box.set_margin_start(self._gtk.font_size)
        box.set_margin_end(self._gtk.font_size)
        scroll = self._gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.add(box)
        page.pack_start(scroll, True, True, 0)
        intro = Gtk.Label(
            label=_("Returns the printer to the Snapmaker firmware. Plug in "
                    "a USB stick with the contents of the stock firmware zip "
                    "archive (J1_V....bin and the folder stock-restore)."),
            wrap=True, xalign=0, wrap_mode=Pango.WrapMode.WORD_CHAR)
        box.pack_start(intro, False, False, 0)
        self.info = Gtk.Label(wrap=True, xalign=0,
                              wrap_mode=Pango.WrapMode.WORD_CHAR)
        box.pack_start(self.info, False, False, 0)
        row = Gtk.Box(spacing=self._gtk.font_size)
        self.search = self._gtk.Button("refresh", _("Search USB Stick"),
                                       "color2")
        self.search.connect("clicked", self._scan)
        self.restore = self._gtk.Button("warning", _("Restore Stock Firmware"),
                                        "color1")
        self.restore.connect("clicked", self._ask)
        for button in (self.search, self.restore):
            button.set_vexpand(False)
            row.pack_start(button, True, True, 0)
        page.pack_end(row, False, False, 0)
        self.content.add(page)

    def activate(self):
        self._scan(None)

    def _scan(self, widget):
        self.package = None
        self.restore.set_sensitive(False)
        self.info.set_label(_("Searching the USB stick..."))
        # Let the label show before the search blocks
        GLib.timeout_add(100, self._do_scan)

    def _do_scan(self):
        try:
            result = run_tool("scan")
            found = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            logging.exception("Stock firmware scan failed")
            self.info.set_label(_("The USB stick could not be read: %s") % e)
            return False
        lines = []
        if not found["sticks"]:
            lines.append(_("No USB stick found."))
        elif not found["packages"]:
            lines.append(_("No Snapmaker update package (J1_V....bin) on the"
                           " USB stick."))
        for package in found["packages"]:
            lines.append(_("Package: %s (main controller %s)")
                         % (package["name"], package["mc_version"]))
        if found["system"]:
            lines.append(_("Snapmaker system: found"))
        lines += found["errors"]
        if len(found["packages"]) > 1:
            lines.append(_("Leave only one package on the USB stick."))
        self.info.set_label("\n".join(lines))
        if len(found["packages"]) == 1 and found["system"]:
            self.package = found["packages"][0]
            self.restore.set_sensitive(True)
        return False

    def _ask(self, widget):
        state = self._printer.get_stat("print_stats", "state")
        if state in BUSY_STATES:
            self._screen.show_popup_message(_("Not possible while printing."))
            return
        buttons = [
            {"name": _("Restore"), "response": Gtk.ResponseType.OK,
             "style": "dialog-error"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-info"},
        ]
        label = Gtk.Label(
            label=_("The printer gets the Snapmaker firmware %s and the "
                    "Snapmaker system as it was before Klipper. Klipper, its "
                    "settings, calibrations and files on the printer are "
                    "deleted.\n\nThe screen shows the progress; the printer "
                    "restarts by itself. Do not switch it off and leave the "
                    "USB stick plugged in.")
            % (self.package["name"],),
            wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        label.set_halign(Gtk.Align.CENTER)
        label.set_valign(Gtk.Align.CENTER)
        self._gtk.Dialog(_("Stock Firmware"), buttons, label, self._response)

    def _response(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id != Gtk.ResponseType.OK or not self.package:
            return
        logging.info("Restoring the stock firmware from %s",
                     self.package["path"])
        try:
            subprocess.run(["sudo", "-n", "systemd-run", "--unit", UNIT,
                            "--collect", PYTHON, os.path.realpath(SCRIPT),
                            "restore", self.package["path"]],
                           check=True, capture_output=True, timeout=30)
        except (OSError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as e:
            logging.exception("Starting the stock firmware restore failed")
            self._screen.show_popup_message(
                _("The restore could not be started: %s") % (e,))
            return
        self.info.set_label(_("Restoring the stock firmware..."))
        self.search.set_sensitive(False)
        self.restore.set_sensitive(False)
