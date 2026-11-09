# WLAN symbol in the title bar of KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import socket

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

# Seconds between two readings of the connection
POLL = 5
# Signal strength (%) to symbol, as the WLAN page of KlipperScreen
LEVELS = ((75, "wifi_excellent"), (60, "wifi_good"), (30, "wifi_fair"),
          (-1, "wifi_weak"))
# Without a connection: the full symbol, greyed out
OFFLINE_ICON = "wifi_excellent"
OFFLINE_OPACITY = .3
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
            name = next(icon for level, icon in LEVELS
                        if status["signal"] > level)
            shown = (name, 1.)
        else:
            shown = (OFFLINE_ICON, OFFLINE_OPACITY)
        if shown != self.shown:
            self.image.set_from_pixbuf(self.screen.gtk.PixbufFromIcon(
                shown[0], self.size, self.size))
            self.image.set_opacity(shown[1])
            self.shown = shown
        self.box.show()
        return True

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
