# Webcam support of the Snapmaker J1, for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# A USB camera streams to Mainsail.  scripts/snapmaker_j1_webcam.sh (as
# root) installs the streamer (ustreamer) and sets up the stream; here the
# add-on sets it up at every start, asks once to install the streamer when
# a camera is plugged in without it, and adds the camera to the webcams of
# Mainsail (Moonraker) when there is none for the stream yet.
import logging
import os
import shutil
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                      "scripts", "snapmaker_j1_webcam.sh")
INSTALL_UNIT = "snapmaker-j1-webcam-install"
DEVICE = "/sys/class/video4linux/video0/device"
# Seconds between two looks for a camera
POLL = 10
BUSY_STATES = ("printing", "paused")
# The webcam in Mainsail (Moonraker), served by nginx
WEBCAM = {
    "name": "J1",
    "location": "printer",
    "service": "mjpegstreamer",
    "target_fps": 15,
    "target_fps_idle": 5,
    "stream_url": "/webcam/?action=stream",
    "snapshot_url": "/webcam/?action=snapshot",
    "aspect_ratio": "16:9",
}


def _camera():
    # A USB camera as /dev/video0 (the stream of the udev rule)
    try:
        return "/usb" in os.path.realpath(DEVICE)
    except OSError:
        return False


def _streamer():
    return shutil.which("ustreamer") is not None


def _run(*args, timeout=120):
    return subprocess.run(["sudo", "-n", "bash", os.path.realpath(SCRIPT)]
                          + list(args), capture_output=True, text=True,
                          timeout=timeout)


class Webcam:
    def __init__(self, screen):
        self.screen = screen
        self.asked = False
        self.installing = False
        self.registered = False
        if _streamer():
            threading.Thread(target=self._setup, daemon=True).start()
        GLib.timeout_add_seconds(POLL, self._poll)

    def _setup(self):
        try:
            result = _run("setup")
            logging.info("Webcam: %s", (result.stdout + result.stderr).strip())
        except (OSError, subprocess.SubprocessError):
            logging.exception("Webcam: setting up the stream failed")

    def _poll(self):
        if self.installing or not _camera():
            return True
        if _streamer():
            if not self.registered:
                self._register()
        elif not self.asked:
            self._ask()
        return True

    # Mainsail shows the webcams Moonraker knows; the camera is added once,
    # so changes made in Mainsail (name, rotation) are kept
    def _register(self):
        ws = getattr(self.screen, "_ws", None)
        if ws is None:
            return

        def listed(result, method, params, *args):
            try:
                webcams = result["result"]["webcams"]
            except (KeyError, TypeError):
                return
            if any("/webcam/" in (cam.get("stream_url") or "")
                   for cam in webcams):
                self.registered = True
                return
            ws.send_method("server.webcams.post_item", dict(WEBCAM), added)

        def added(result, method, params, *args):
            if "result" in (result or {}):
                logging.info("Webcam: added to Mainsail")
                self.registered = True
            else:
                logging.error("Webcam: adding to Mainsail failed: %s", result)

        ws.send_method("server.webcams.list", {}, listed)

    def _ask(self):
        screen = self.screen
        printer = screen.printer
        if (printer is None or screen.dialogs
                or printer.get_stat("print_stats", "state") in BUSY_STATES):
            return
        self.asked = True
        label = Gtk.Label(hexpand=True, vexpand=True, halign=Gtk.Align.CENTER,
                          valign=Gtk.Align.CENTER, wrap=True,
                          wrap_mode=Pango.WrapMode.WORD_CHAR,
                          justify=Gtk.Justification.CENTER,
                          max_width_chars=48)
        label.set_markup("%s\n\n%s" % (
            GLib.markup_escape_text(_("A camera was connected.")),
            GLib.markup_escape_text(
                _("Install the webcam support? The camera then shows in the"
                  " web interface (Mainsail). The installation needs the"
                  " network and takes several minutes; printing is"
                  " possible meanwhile."))))
        buttons = [
            {"name": _("Install"), "response": Gtk.ResponseType.OK,
             "style": "dialog-info"},
            {"name": _("Later"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-secondary"},
        ]
        screen.gtk.Dialog(_("Webcam"), buttons, label, self._response)

    def _response(self, dialog, response_id):
        self.screen.gtk.remove_dialog(dialog)
        if response_id != Gtk.ResponseType.OK:
            return
        try:
            subprocess.run(["sudo", "-n", "systemd-run", "--unit",
                            INSTALL_UNIT, "--collect", "bash",
                            os.path.realpath(SCRIPT), "install"],
                           check=True, capture_output=True, timeout=30)
        except (OSError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            logging.exception("Webcam: starting the installation failed")
            self.screen.show_popup_message(
                _("The webcam support could not be installed"))
            return
        self.installing = True
        self.screen.show_popup_message(
            _("Installing the webcam support..."), 1)
        GLib.timeout_add_seconds(POLL, self._installed)

    def _installed(self):
        state = subprocess.run(
            ["systemctl", "is-active", INSTALL_UNIT], capture_output=True,
            text=True).stdout.strip()
        if state in ("active", "activating"):
            return True
        self.installing = False
        if _streamer():
            self.screen.show_popup_message(
                _("Webcam ready: it shows in the web interface"), 1)
            self._register()
        else:
            self.screen.show_popup_message(
                _("The webcam support could not be installed (network?)"))
        return False
