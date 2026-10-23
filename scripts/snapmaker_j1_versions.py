#!/usr/bin/env python3
# Pin Klipper, Moonraker and KlipperScreen in the update manager to the
# versions of versions.conf
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Moonraker reads moonraker/KlipperSnapmakerJ1.conf (included from
# moonraker.conf), so the pins arrive with an update of this repository.
# Run after changing versions.conf; --check fails when the two differ.
import argparse, os, sys

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSIONS = os.path.join(REPO_DIR, "versions.conf")
MOONRAKER_CONF = os.path.join(REPO_DIR, "moonraker", "KlipperSnapmakerJ1.conf")
BEGIN = "# --- pinned versions (scripts/snapmaker_j1_versions.py) ---"
END = "# --- end of pinned versions ---"


def read_versions():
    versions = []
    with open(VERSIONS) as f:
        for line in f:
            fields = line.split()
            if fields and not fields[0].startswith("#"):
                versions.append((fields[0], fields[1], fields[2]))
    return versions


def pin_block(versions):
    lines = [BEGIN]
    for name, commit, version in versions:
        lines += ["", "# %s %s" % (name, version),
                  "[update_manager %s]" % (name,),
                  "pinned_commit: %s" % (commit,)]
    lines += ["", END]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="only check that the pins match versions.conf")
    args = parser.parse_args()
    with open(MOONRAKER_CONF) as f:
        conf = f.read()
    if BEGIN not in conf or END not in conf:
        sys.exit("%s: no pinned versions block" % (MOONRAKER_CONF,))
    start = conf.index(BEGIN)
    end = conf.index(END) + len(END) + 1
    new = conf[:start] + pin_block(read_versions()) + conf[end:]
    if args.check:
        if new != conf:
            sys.exit("The pinned versions differ from versions.conf; run"
                     " scripts/snapmaker_j1_versions.py")
        print("Pinned versions match versions.conf")
        return
    with open(MOONRAKER_CONF, "w", newline="\n") as f:
        f.write(new)
    print("Pinned versions written to %s" % (MOONRAKER_CONF,))


if __name__ == "__main__":
    main()
