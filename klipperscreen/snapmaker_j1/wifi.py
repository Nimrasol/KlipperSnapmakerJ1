# WLAN symbol in the title bar of KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import socket
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gio, GLib, Gtk, Pango

from . import style

# Seconds between two readings of the connection
POLL = 5
NM = "org.freedesktop.NetworkManager"
DEVICE_TYPE_WIFI = 2
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
# The parts without signal stay visible in grey (as disabled elements);
# without a connection the whole symbol is grey
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
        # The last reading (None: no WLAN device) and whether one runs
        self.status = None
        self.reading = False
        base = screen.base_panel
        self.size = screen.gtk.img_scale * base.bts
        self.image = Gtk.Image()
        self.box = Gtk.EventBox(no_show_all=True)
        self.box.add(self.image)
        # A finger-sized tap area around the small symbol (the event box
        # takes the full height of the title bar)
        self.image.set_margin_start(screen.gtk.font_size * 2)
        self.image.set_margin_end(screen.gtk.font_size)
        self.box.connect("button-press-event", self._clicked)
        # Left of the clock
        titlebar = base.titlebar
        titlebar.add(self.box)
        titlebar.reorder_child(
            self.box, titlebar.get_children().index(base.control["time_box"]))
        self.image.show()
        self._update()
        GLib.timeout_add_seconds(POLL, self._update)

    def _bus(self):
        # NetworkManager's properties over GLib's D-Bus, not KlipperScreen's
        # network module (its interface changes between versions) nor
        # sdbus-networkmanager (loading its blocking and its asynchronous
        # flavour in one process fails, and KlipperScreen uses the latter)
        if self.nm is None:
            try:
                self.nm = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            except GLib.Error:
                if not self.nm_failed:
                    logging.exception("WLAN symbol: no system bus")
                self.nm_failed = True
        return self.nm

    def _get(self, path, interface, name):
        return self.nm.call_sync(
            NM, path, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (NM + interface, name)),
            GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 2000,
            None).unpack()[0]

    def _status(self):
        # None without a WLAN device, else the connection (ssid empty when
        # not connected).  The devices are read every time: NetworkManager
        # may start after KlipperScreen (it waits for the WLAN firmware), and
        # the WLAN device may come up later or be created anew
        if self._bus() is None:
            return None
        wlan = None
        for path in self._get("/org/freedesktop/NetworkManager", "",
                              "Devices"):
            if self._get(path, ".Device", "DeviceType") == DEVICE_TYPE_WIFI:
                wlan = path
                break
        if wlan is None:
            return None
        status = {"ssid": "", "signal": 0, "ip": "?"}
        ap = self._get(wlan, ".Device.Wireless", "ActiveAccessPoint")
        if ap == "/":
            return status
        status["ssid"] = bytes(self._get(ap, ".AccessPoint", "Ssid")).decode(
            "utf-8", errors="ignore")
        status["signal"] = self._get(ap, ".AccessPoint", "Strength")
        # A connection without a lease yet reports "/"
        config = self._get(wlan, ".Device", "Ip4Config")
        if config != "/":
            addresses = self._get(config, ".IP4Config", "AddressData")
            if addresses:
                status["ip"] = addresses[0]["address"]
        return status

    def _update(self):
        # Read in a thread: a NetworkManager that does not answer (eg a
        # hanging WLAN firmware) would block the touch screen for seconds
        if not self.reading:
            self.reading = True
            threading.Thread(target=self._read, daemon=True).start()
        return True

    def _read(self):
        try:
            status = self._status()
        except Exception:
            logging.exception("WLAN symbol: reading the connection failed")
            status = None
        GLib.idle_add(self._show, status)

    def _show(self, status):
        self.reading = False
        self.status = status
        if status is None:
            self.box.hide()
            return False
        if status["ssid"]:
            parts = next(n for level, n in LEVELS if status["signal"] > level)
            shown = parts
        else:
            shown = 0
        if shown != self.shown:
            self.image.set_from_pixbuf(self._pixbuf(shown))
            self.shown = shown
        self.box.show()
        return False

    def _pixbuf(self, parts):
        # The first parts in orange (signal), the others in grey
        paths = "".join(
            '<path d="%s" fill="%s"/>' % (
                d, style.PRIMARY if i < parts else style.DISABLED)
            for i, d in enumerate(PARTS))
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"'
               ' viewBox="0 0 24 24">%s</svg>' % (paths,))
        loader = GdkPixbuf.PixbufLoader()
        loader.set_size(int(self.size), int(self.size))
        loader.write(svg.encode())
        loader.close()
        return loader.get_pixbuf()

    def _clicked(self, widget, event):
        # The last reading (at most POLL seconds old)
        status = self.status
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
            # The IP address first: <name>.local needs mDNS, which some
            # networks block
            if status["ip"] != "?":
                lines.append(GLib.markup_escape_text(
                    "http://%s" % (status["ip"],)))
            lines.append(GLib.markup_escape_text(
                "http://%s.local" % (socket.gethostname(),)))
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
