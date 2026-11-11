# WLAN symbol in the title bar of KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import socket

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, GLib, Gtk, Pango

from . import style

# Seconds between two readings of the connection
POLL = 5
# The parts of the WLAN symbol of the theme (wifi_excellent.svg): the dot
# and the two arcs, from the inside out
PARTS = (
    "M12,21L15.6,16.2C14.6,15.45 13.35,15 12,15C10.65,15 9.4,15.45 8.4,16.2"
    "L12,21Z",
    "M12,9C9.3,9 6.81,9.89 4.8,11.4L6.6,13.8C8.1,12.67 9.97,12 12,12"
    "C14.03,12 15.9,12.67 17.4,13.8L19.2,11.4C17.19,9.89 14.7,9 12,9Z",
    "M12,3C7.95,3 4.21,4.34 1.2,6.6L3,9C5.5,7.12 8.62,6 12,6C15.38,6 18.5,7.12"
    " 21,9L22.8,6.6C19.79,4.34 16.05,3 12,3Z",
)
# Signal strength (%) to the number of parts shown in orange, as the levels
# of the WLAN page of KlipperScreen (excellent, good, fair and weak)
LEVELS = ((75, 3), (60, 2), (-1, 1))
# The parts without signal stay visible in the color of the title bar;
# without a connection the whole symbol is in that color, dimmed
OFFLINE_OPACITY = .5
# The WLAN page (More -> Network -> WLAN)
WLAN_PANEL = "network"


class WifiIcon:
    # The symbol shows the WLAN connection at a glance (signal strength,
    # greyed out without a connection); a tap opens a window with the
    # network, the signal, the IP address and the address of the web
    # interface.  The values come from NetworkManager, as on the WLAN page.
    def __init__(self, screen):
        self.screen = screen
        self.nm = None
        self.nm_failed = False
        self.shown = None
        base = screen.base_panel
        self.size = screen.gtk.img_scale * base.bts
        self.image = Gtk.Image()
        self.box = Gtk.EventBox(no_show_all=True)
        self.box.add(self.image)
        self.box.connect("button-press-event", self._clicked)
        # Left of the clock
        titlebar = base.titlebar
        titlebar.add(self.box)
        titlebar.reorder_child(
            self.box, titlebar.get_children().index(base.control["time_box"]))
        self.image.show()
        self._update()
        GLib.timeout_add_seconds(POLL, self._update)

    def _sdbus_nm(self):
        if self.nm is None and not self.nm_failed:
            try:
                from ks_includes.sdbus_nm import SdbusNm
                self.nm = SdbusNm(
                    lambda msg, *args: logging.info("WLAN: %s", msg))
            except Exception:
                logging.exception("WLAN symbol: NetworkManager not available")
                self.nm_failed = True
        return self.nm

    def _status(self):
        # None without a WLAN device, else the connection (ssid empty when
        # not connected)
        nm = self._sdbus_nm()
        if nm is None or not getattr(nm, "wlan_device", None):
            return None
        status = {"ssid": "", "signal": 0, "ip": "?"}
        ap = nm.get_connected_ap()
        if ap is None:
            return status
        status["ssid"] = ap.ssid.decode("utf-8", errors="ignore")
        status["signal"] = ap.strength
        status["ip"] = nm.get_ip_for_interface(nm.wlan_device.interface)
        return status

    def _update(self):
        try:
            status = self._status()
        except Exception:
            logging.exception("WLAN symbol: reading the connection failed")
            status = None
        if status is None:
            self.box.hide()
            return not self.nm_failed
        if status["ssid"]:
            parts = next(n for level, n in LEVELS if status["signal"] > level)
            shown = (parts, 1.)
        else:
            shown = (0, OFFLINE_OPACITY)
        if shown != self.shown:
            self.image.set_from_pixbuf(self._pixbuf(shown[0]))
            self.image.set_opacity(shown[1])
            self.shown = shown
        self.box.show()
        return True

    def _pixbuf(self, parts):
        # The first parts in orange (signal), the others in the color of the
        # title bar
        paths = "".join(
            '<path d="%s" fill="%s"/>' % (
                d, style.PRIMARY if i < parts else style.BODY)
            for i, d in enumerate(PARTS))
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
               ' viewBox="0 0 24 24">%s</svg>' % (paths,))
        loader = GdkPixbuf.PixbufLoader()
        loader.set_size(int(self.size), int(self.size))
        loader.write(svg.encode())
        loader.close()
        return loader.get_pixbuf()

    def _clicked(self, widget, event):
        self._update()
        try:
            status = self._status()
        except Exception:
            logging.exception("WLAN symbol: reading the connection failed")
            status = None
        lines = []
        if status and status["ssid"]:
            lines.append("<b>%s</b>" % GLib.markup_escape_text(status["ssid"]))
            lines.append("")
            lines.append(GLib.markup_escape_text(
                "%s: %d %%" % (_("Signal"), status["signal"])))
            lines.append(GLib.markup_escape_text(
                "%s: %s" % (_("IP address"), status["ip"])))
            lines.append("")
            lines.append(GLib.markup_escape_text(
                _("Web interface (Mainsail):")))
            lines.append(GLib.markup_escape_text(
                "http://%s.local" % (socket.gethostname(),)))
            if status["ip"] != "?":
                lines.append(GLib.markup_escape_text(
                    "http://%s" % (status["ip"],)))
        else:
            lines.append("<b>%s</b>" % GLib.markup_escape_text(
                _("Not connected")))
            lines.append("")
            lines.append(GLib.markup_escape_text(
                _("Connect the printer on the WLAN page.")))
        # As the other dialogs of the add-on: a centered block of text
        label = Gtk.Label(hexpand=True, vexpand=True, halign=Gtk.Align.CENTER,
                          valign=Gtk.Align.CENTER, wrap=True,
                          wrap_mode=Pango.WrapMode.WORD_CHAR,
                          justify=Gtk.Justification.CENTER,
                          max_width_chars=48)
        label.set_markup("\n".join(lines))
        buttons = [
            {"name": _("WLAN"), "response": Gtk.ResponseType.APPLY,
             "style": "dialog-info"},
            {"name": _("Close"), "response": Gtk.ResponseType.CLOSE,
             "style": "dialog-secondary"},
        ]

        def response(dialog, response_id):
            self.screen.gtk.remove_dialog(dialog)
            if response_id == Gtk.ResponseType.APPLY:
                self.screen.show_panel(WLAN_PANEL, _("WLAN"))

        self.screen.gtk.Dialog(_("WLAN"), buttons, label, response)
        return True
