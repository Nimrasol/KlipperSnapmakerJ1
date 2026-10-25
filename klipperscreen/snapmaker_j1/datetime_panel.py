# Time zone of the printer for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# The display module has no battery backed clock, so the time comes from
# the network; only the time zone is set here.
import logging
import subprocess
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

from . import settings

# systemd-timedated sets the time zone; the OS image allows it for the
# user of KlipperScreen (polkit)
TIMEDATE = ["busctl", "call", "org.freedesktop.timedate1",
            "/org/freedesktop/timedate1", "org.freedesktop.timedate1"]
# Seconds after a zone list appears during which taps are ignored
ZONE_TAP_DELAY = .4


def show_clock():
    return bool(settings.get("show_clock", True))


def apply_clock(screen):
    # The clock in the title bar of KlipperScreen
    label = screen.base_panel.control.get("time")
    if label is not None:
        shown = show_clock()
        label.set_no_show_all(not shown)
        label.set_visible(shown)


def set_show_clock(screen, shown):
    settings.save("show_clock", bool(shown))
    apply_clock(screen)


def _timedate(method, signature, *args):
    result = subprocess.run(TIMEDATE + [method, signature] + list(args),
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "failed")


def _settings():
    result = subprocess.run(["timedatectl", "show"], capture_output=True,
                            text=True, timeout=10)
    return dict(line.split("=", 1) for line in result.stdout.splitlines()
                if "=" in line)


def _timezones():
    result = subprocess.run(["timedatectl", "list-timezones"],
                            capture_output=True, text=True, timeout=10)
    return result.stdout.split()


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or _("Clock"))
        self.clock_timer = None
        self.region = None
        self.shown_at = 0.
        self.page = self._build_page()
        self.content.add(self.page)

    def _build_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                      spacing=self._gtk.font_size, vexpand=True)
        box.set_margin_start(self._gtk.font_size)
        box.set_margin_end(self._gtk.font_size)
        self.clock = Gtk.Label(xalign=0)
        box.pack_start(self.clock, False, False, 0)

        row = Gtk.Box(spacing=self._gtk.font_size, hexpand=True)
        row.pack_start(Gtk.Label(label=_("Time zone"), xalign=0,
                                 hexpand=True), True, True, 0)
        self.zone = Gtk.Label(xalign=1)
        row.pack_start(self.zone, False, False, 0)
        change = self._gtk.Button(None, _("Change"), "color1", scale=.66)
        change.set_vexpand(False)
        change.set_hexpand(False)
        change.connect("clicked", self._choose_zone)
        row.pack_start(change, False, False, 0)
        box.pack_start(row, False, False, 0)

        self.sync = Gtk.Label(xalign=0, wrap=True,
                              wrap_mode=Pango.WrapMode.WORD_CHAR)
        box.pack_start(self.sync, False, False, 0)

        row = Gtk.Box(spacing=self._gtk.font_size, hexpand=True)
        row.pack_start(Gtk.Label(label=_("Show the clock in the title bar"),
                                 xalign=0, hexpand=True), True, True, 0)
        self.clock_switch = Gtk.Switch(active=show_clock(),
                                       valign=Gtk.Align.CENTER)
        self.clock_switch.connect("notify::active", self._clock_toggled)
        row.pack_start(self.clock_switch, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box

    def _clock_toggled(self, switch, param):
        set_show_clock(self._screen, switch.get_active())

    def activate(self):
        self._load()
        self._tick()
        if self.clock_timer is None:
            self.clock_timer = GLib.timeout_add_seconds(1, self._tick)

    def deactivate(self):
        if self.clock_timer is not None:
            GLib.source_remove(self.clock_timer)
            self.clock_timer = None

    def _load(self):
        settings = _settings()
        self.zone.set_label(settings.get("Timezone", "?"))
        if settings.get("NTPSynchronized") == "yes":
            self.sync.set_label(_("The time is set from the network."))
        else:
            self.sync.set_label(
                _("The time is not synchronized yet (no network?). The "
                  "display has no battery backed clock: without network "
                  "the printer continues from the time saved last before "
                  "it was switched off."))

    def _tick(self):
        self.clock.set_label(time.strftime("%Y-%m-%d  %H:%M:%S"))
        return True

    # Time zone: region, then city
    def _choose_zone(self, widget):
        self.region = None
        self._show_zones()

    def _show_zones(self):
        zones = _timezones()
        if self.region is None:
            items = sorted({z.split("/")[0] for z in zones if "/" in z})
            items.append("UTC")
        else:
            prefix = self.region + "/"
            items = [z[len(prefix):] for z in zones if z.startswith(prefix)]
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           homogeneous=True, max_children_per_line=4,
                           valign=Gtk.Align.START)
        for item in items:
            button = self._gtk.Button(None, item.replace("_", " "), "color3",
                                      scale=.66)
            button.set_vexpand(False)
            button.connect("clicked", self._zone_selected, item)
            flow.add(button)
        scroll = self._gtk.ScrolledWindow()
        scroll.add(flow)
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(scroll)
        self.content.show_all()
        self.shown_at = time.monotonic()

    def _zone_selected(self, widget, item):
        # The tap that opened this list must not also pick the button that
        # appears under the finger
        if time.monotonic() - self.shown_at < ZONE_TAP_DELAY:
            return
        if self.region is None and item != "UTC":
            self.region = item
            self._show_zones()
            return
        zone = item if self.region is None else self.region + "/" + item
        try:
            _timedate("SetTimezone", "sb", zone, "false")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
            logging.exception("Setting the time zone failed")
            self._screen.show_popup_message(
                _("The time zone could not be changed: %s") % (e,))
            return
        # This process (and its clock in the title bar) follows at once
        time.tzset()
        logging.info("Time zone set to %s", zone)
        self._back_to_page()

    def _back_to_page(self):
        self.region = None
        for child in self.content.get_children():
            self.content.remove(child)
        self.content.add(self.page)
        self._load()
        self.page.show_all()

    def back(self):
        # Back from the zone lists to the region list and the main page
        if self.page.get_parent() is None:
            if self.region is not None:
                self.region = None
                self._show_zones()
            else:
                self._back_to_page()
            return True
        return False
