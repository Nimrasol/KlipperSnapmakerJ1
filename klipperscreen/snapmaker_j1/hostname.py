# Network name of the printer (<name>.local) for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import re
import socket
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

# A single DNS label: what <name>.local and the host name allow
VALID_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
# NetworkManager stores the host name (/etc/hostname), avahi announces
# <name>.local without a restart; both allow it for the group netdev
SAVE_COMMANDS = [
    ["busctl", "call", "org.freedesktop.NetworkManager",
     "/org/freedesktop/NetworkManager/Settings",
     "org.freedesktop.NetworkManager.Settings", "SaveHostname", "s"],
    ["busctl", "call", "org.freedesktop.Avahi", "/",
     "org.freedesktop.Avahi.Server", "SetHostName", "s"],
]


def save_hostname(name):
    for cmd in SAVE_COMMANDS:
        result = subprocess.run(cmd + [name], capture_output=True, text=True,
                                timeout=10)
        # avahi refuses to set the name it already has
        if result.returncode and "redundant" not in result.stderr:
            raise RuntimeError(result.stderr.strip() or "failed")


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _("Network Name"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      spacing=self._gtk.font_size, vexpand=True)
        box.set_margin_start(self._gtk.font_size)
        box.set_margin_end(self._gtk.font_size)
        intro = Gtk.Label(
            label=_("Name of this printer in the network. Give each printer"
                    " its own name when you have several."),
            wrap=True, xalign=0, wrap_mode=Pango.WrapMode.WORD_CHAR)
        box.pack_start(intro, False, False, 0)
        row = Gtk.Box(spacing=self._gtk.font_size)
        self.entry = Gtk.Entry(hexpand=True)
        self.entry.connect("touch-event", self._screen.show_keyboard)
        self.entry.connect("button-press-event", self._screen.show_keyboard)
        self.entry.connect("activate", self._save)
        self.entry.connect("changed", self._changed)
        row.pack_start(self.entry, True, True, 0)
        self.save = self._gtk.Button("complete", _("Save"), "color1")
        # KlipperScreen buttons fill the page height by default
        self.save.set_hexpand(False)
        self.save.set_vexpand(False)
        self.save.connect("clicked", self._save)
        row.pack_start(self.save, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.info = Gtk.Label(wrap=True, xalign=0,
                              wrap_mode=Pango.WrapMode.WORD_CHAR)
        box.pack_start(self.info, False, False, 0)
        self.content.add(box)

    def activate(self):
        self.current = socket.gethostname()
        self.entry.set_text(self.current)
        self._show_address(self.current)

    def deactivate(self):
        self._screen.remove_keyboard()

    def _name(self):
        return self.entry.get_text().strip().lower()

    def _changed(self, widget):
        name = self._name()
        valid = bool(VALID_NAME.match(name))
        self.save.set_sensitive(valid and name != self.current)
        if not valid:
            self.info.set_label(
                _("Use letters a-z, digits and '-' (not at the start or"
                  " end), at most 63 characters."))
        else:
            self._show_address(name)

    def _show_address(self, name):
        self.info.set_label(_("Web interface (Mainsail):") + " http://%s.local"
                            % (name,))

    def _save(self, widget):
        name = self._name()
        if not VALID_NAME.match(name) or name == self.current:
            return
        try:
            save_hostname(name)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
            logging.exception("Setting the host name to %s failed", name)
            self._screen.show_popup_message(
                _("The network name could not be changed: %s") % (e,))
            return
        logging.info("Network name changed from %s to %s", self.current,
                     name)
        self.current = name
        self._screen.remove_keyboard()
        self.save.set_sensitive(False)
        self._show_address(name)
        self._screen.show_popup_message(
            _("Network name changed to %s") % (name,), level=1)
