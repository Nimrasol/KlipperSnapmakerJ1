# The J1 buttons on the dashboard of Mainsail
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Mainsail lists every macro in one long "Macros" panel, where the print
# mode choice (SNAPMAKER_PRINT_MODE) is lost among the G-code compatibility
# macros.  As long as nobody has set up the macros of Mainsail, this puts
# them in its "expert" mode with one macro group "Snapmaker J1", which
# Mainsail shows as a panel on its dashboard.  The settings are Mainsail's
# own (its namespace in the Moonraker database); they are written only if
# Mainsail has been opened once (its namespace exists) and has no macro
# settings yet, so a user's own setup is never changed.  The panel goes
# above the toolhead panel in the first column of each dashboard layout
# that still is Mainsail's default.  KlipperScreen checks this when
# Klipper becomes ready.
import logging

NAMESPACE = "mainsail"
GROUP_ID = "snapmaker-j1"


def _macro(pos, name, standby=True, printing=False, pause=False):
    return {"pos": pos, "name": name, "color": "group",
            "showInStandby": standby, "showInPrinting": printing,
            "showInPause": pause}


GROUP = {
    "id": GROUP_ID,
    "name": "Snapmaker J1",
    "color": "primary",
    "showInStandby": True,
    "showInPrinting": True,
    "showInPause": True,
    "macros": [
        _macro(1, "SNAPMAKER_PRINT_MODE"),
        _macro(2, "SNAPMAKER_LOAD_FILAMENT", pause=True),
        _macro(3, "SNAPMAKER_UNLOAD_FILAMENT", pause=True),
        _macro(4, "SNAPMAKER_PAUSE_HEAT", standby=False, pause=True),
        _macro(5, "SNAPMAKER_NOISE_MODE", printing=True),
    ],
}


PANEL = "macrogroup_" + GROUP_ID
# The first column of each dashboard layout as Mainsail (v2.19) has it by
# default
LAYOUTS = {
    "mobileLayout": ["webcam", "toolhead-control", "extruder-control",
                     "macros", "machine-settings", "miscellaneous",
                     "temperature", "miniconsole"],
    "tabletLayout1": ["webcam", "toolhead-control", "extruder-control",
                      "macros", "machine-settings", "miscellaneous"],
    "desktopLayout1": ["webcam", "toolhead-control", "extruder-control",
                       "macros", "machine-settings", "miscellaneous"],
    "widescreenLayout1": ["toolhead-control", "extruder-control", "macros",
                          "miscellaneous"],
}
HIDDEN = {"mobileLayout": ["webcam", "miniconsole"]}


def _layout(name):
    panels = []
    for panel in LAYOUTS[name]:
        if panel == "toolhead-control":
            panels.append({"name": PANEL, "visible": True})
        panels.append({"name": panel,
                       "visible": panel not in HIDDEN.get(name, [])})
    return panels


def setup(screen):
    def got(response, method, params):
        result = response.get("result")
        if result is None:
            # No Mainsail namespace yet: Mainsail fills it with its
            # defaults when it is opened the first time
            return False
        value = result.get("value") or {}
        macros = value.get("macros")
        if macros is None:
            logging.info("Mainsail: adding the Snapmaker J1 macro group")
            _post(screen, "macros.macrogroups." + GROUP_ID, GROUP)
            _post(screen, "macros.mode", "expert")
        elif GROUP_ID not in (macros.get("macrogroups") or {}):
            return False
        dashboard = value.get("dashboard") or {}
        for name in LAYOUTS:
            if name not in dashboard:
                logging.info("Mainsail: J1 panel on top of %s", name)
                _post(screen, "dashboard." + name, _layout(name))
        return False

    screen._ws.send_method("server.database.get_item",
                           {"namespace": NAMESPACE}, got)


def _post(screen, key, value):
    screen._ws.send_method("server.database.post_item", {
        "namespace": NAMESPACE, "key": key, "value": value})
