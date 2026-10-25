# Settings of the KlipperScreen add-on
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# KlipperScreen drops unknown options from its own configuration when it
# starts, so the add-on keeps its settings in a file of its own.
import json
import logging
import os

SETTINGS_FILE = os.path.expanduser("~/.config/snapmaker_j1/klipperscreen.json")


def load():
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get(name, default):
    return load().get(name, default)


def save(name, value):
    settings = load()
    settings[name] = value
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except OSError:
        logging.exception("Saving %s failed", SETTINGS_FILE)
