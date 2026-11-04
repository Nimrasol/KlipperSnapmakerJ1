# Notice of a new release for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Asks once per release of KlipperSnapmakerJ1 whether to update, so the
# user learns about it without opening the update panel.  "Later" leaves
# the update in the update panel; the next release asks again.
#
# Moonraker restarts only Klipper and itself after an update of this
# repository (it may only manage klipper, moonraker or a service of the
# entry's own name), so the add-on would keep running its old code.
# AddonReload restarts KlipperScreen once the code it runs has changed.
import logging
import os
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from . import settings

NAME = "KlipperSnapmakerJ1"
# The release last asked for (settings)
NOTIFIED = "update_notified"
# Seconds after Klipper is ready before the first check, and between the
# checks (Moonraker refreshes on its own: at its start, when the WLAN
# connects and once a week; the status is only read here)
FIRST_CHECK_DELAY = 60
CHECK_INTERVAL = 3600
# What KlipperScreen runs of this repository
REPO = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..")
CODE_PATHS = ("HEAD:klipperscreen", "HEAD:scripts")
# Seconds between the tries while KlipperScreen is in use
RELOAD_RETRY = 10
# Panels that guide through something on the printer
BUSY_PANELS = ("snapmaker_calibration", "snapmaker_filament")


def _code_version():
    try:
        return subprocess.run(
            ["git", "-C", REPO, "rev-parse"] + list(CODE_PATHS),
            capture_output=True, text=True, timeout=10,
            check=True).stdout
    except (OSError, subprocess.SubprocessError):
        logging.exception("Reading the version of the add-on failed")
        return None


class AddonReload:
    def __init__(self, screen):
        self.screen = screen
        self.running = _code_version()
        self.retry = None

    # An update restarts Klipper, so this is the moment to look
    def klipper_ready(self):
        if self.retry is not None or self.running is None:
            return
        current = _code_version()
        if current is None or current == self.running:
            return
        logging.info("The add-on was updated, restarting KlipperScreen")
        self.retry = GLib.timeout_add_seconds(RELOAD_RETRY, self._try)

    def _try(self):
        screen = self.screen
        printer = screen.printer
        panels = screen._cur_panels
        if (printer is None or printer.state != "ready" or screen.dialogs
                or screen.state.updating
                or screen.snapmaker_calibration_print
                or (panels and panels[-1] in BUSY_PANELS)):
            return True
        logging.info("Restarting KlipperScreen for the new add-on")
        screen.restart_ks()
        return False


class UpdateNotice:
    def __init__(self, screen):
        self.screen = screen
        self.dialog = None
        self.first_check = None
        GLib.timeout_add_seconds(CHECK_INTERVAL, self._timer)

    def klipper_ready(self):
        if self.first_check is None:
            self.first_check = GLib.timeout_add_seconds(
                FIRST_CHECK_DELAY, self._first_check)

    def _first_check(self):
        self.first_check = None
        self.check()
        return False

    def _timer(self):
        self.check()
        return True

    def _busy(self):
        # Not while printing, over another dialog or the dark screen saver
        # (a touch to wake the display would answer the dialog)
        screen = self.screen
        printer = screen.printer
        return (self.dialog is not None or screen.dialogs
                or screen.state.updating or screen.screensaver.is_showing
                or printer is None
                or printer.state in ("printing", "paused"))

    def check(self):
        if self._busy():
            return
        self.screen._ws.send_method("machine.update.status",
                                    callback=self._status)

    def _status(self, response, method, params):
        try:
            info = response["result"]["version_info"][NAME]
        except (KeyError, TypeError):
            return
        local, remote = info.get("version"), info.get("remote_version")
        if (not info.get("is_valid") or info.get("is_dirty")
                or not remote or remote == "?" or remote == local
                or settings.get(NOTIFIED, None) == remote
                or self._busy()):
            return
        logging.info("Update notice: %s %s -> %s", NAME, local, remote)
        label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        label.set_markup(
            "<span size='x-large'><b>%s</b></span>\n\n%s\n\n<b>%s → %s</b>"
            "\n\n%s" % (
            GLib.markup_escape_text(_("New Update available")),
            _("A new version of the Snapmaker J1 support is available."),
            GLib.markup_escape_text(local or "?"),
            GLib.markup_escape_text(remote),
            _("Update now? Klipper restarts. Afterwards Klipper, Moonraker"
              " and KlipperScreen may have updates as well (More → Update).")))
        buttons = [
            {"name": _("Update"), "response": Gtk.ResponseType.OK,
             "style": "dialog-info"},
            {"name": _("Later"), "response": Gtk.ResponseType.CLOSE,
             "style": "dialog-secondary"},
        ]
        self.dialog = self.screen.gtk.Dialog(
            _("Update available"), buttons, label, self._response, remote)

    def _response(self, dialog, response_id, remote):
        self.screen.gtk.remove_dialog(dialog)
        self.dialog = None
        # Asked once per release, whatever the answer
        settings.save(NOTIFIED, remote)
        if response_id != Gtk.ResponseType.OK:
            return
        screen = self.screen
        if screen.state.updating:
            return
        # As the update panel does it: its progress dialog, then the update
        screen.base_panel.show_update_dialog()
        screen._notification_handler.handle(
            "notify_update_response",
            {"application": {NAME},
             "message": _("Starting update for") + f" {NAME}...",
             "complete": False})
        screen._ws.send_method("machine.update.client", {"name": NAME})
