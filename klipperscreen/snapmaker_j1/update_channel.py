# Release candidates of KlipperSnapmakerJ1 for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# The update manager offers releases (vX.Y.Z, Moonraker channel stable).
# Users who help testing can also take release candidates (vX.Y.Z-rc.N,
# channel beta): the Moonraker entry of KlipperSnapmakerJ1 is then a file
# that includes the one of the repository and sets the channel, instead of
# the link to it that install.sh makes.
import logging
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

ENTRY = os.path.expanduser("~/printer_data/config/snapmaker_j1/moonraker.conf")
REPO_ENTRY = os.path.realpath(os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "..", "..", "moonraker",
    "KlipperSnapmakerJ1.conf"))
RC_CHANNEL = "channel: beta"
RC_ENTRY = """\
# Written by KlipperScreen (More -> Update -> Release candidates): the
# entry of KlipperSnapmakerJ1 with release candidates.  Switching them
# off there links this file to the repository's entry again.
[include %s]

[update_manager KlipperSnapmakerJ1]
%s
""" % (REPO_ENTRY, RC_CHANNEL)


def enabled():
    if os.path.islink(ENTRY):
        return False
    try:
        with open(ENTRY) as f:
            return RC_CHANNEL in f.read()
    except OSError:
        return False


def _write(on):
    tmp = ENTRY + ".tmp"
    if on:
        with open(tmp, "w") as f:
            f.write(RC_ENTRY)
    else:
        os.symlink(REPO_ENTRY, tmp)
    os.replace(tmp, ENTRY)


def add_switch(screen, box):
    # A row at the end of the update panel
    switch = Gtk.Switch(active=enabled(), valign=Gtk.Align.CENTER)
    label = Gtk.Label(wrap=True, hexpand=True, xalign=0)
    label.set_markup("<b>%s</b>\n%s" % (
        _("Release candidates"),
        _("Also offer test versions before a release, to help testing")))
    row = Gtk.Box(spacing=10, vexpand=False)
    row.set_margin_start(10)
    row.set_margin_end(10)
    row.pack_start(label, True, True, 0)
    row.pack_start(switch, False, False, 0)
    box.pack_end(row, False, False, 5)
    switch.connect("notify::active", _toggled, screen)


def _toggled(switch, param, screen):
    on = switch.get_active()
    if on == enabled():
        return
    try:
        _write(on)
    except OSError as e:
        logging.exception("Update channel not changed")
        screen.show_popup_message(_("Not changed: %s") % e)
        switch.set_active(not on)
        return
    logging.info("Release candidates %s", "on" if on else "off")
    # Moonraker reads its configuration only when it starts
    screen._ws.send_method("machine.services.restart",
                           {"service": "moonraker"})
    screen.show_popup_message(
        _("Release candidates on: test versions are offered in the update"
          " menu.") if on else
        _("Release candidates off: only releases are offered."), level=1)
