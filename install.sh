#!/bin/bash
# Install the Snapmaker J1 support into Klipper, KlipperScreen and Moonraker
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Usage: install.sh [--apk base.apk] [--images DIR]
#   --apk     J1 display application to take pictures and test prints from
#   --images  directory with calibration pictures (eg own animations);
#             pictures found there take precedence over the application's
#
# Everything is linked, not copied, so an update of this repository (git
# pull, or the Moonraker update manager) takes effect after a restart of
# Klipper and KlipperScreen.  Klipper and KlipperScreen stay unmodified
# checkouts; the links are excluded from their git status.
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
KS_DIR="${KS_DIR:-$HOME/KlipperScreen}"
DATA_DIR="${DATA_DIR:-$HOME/printer_data}"
CONFIG_DIR="$DATA_DIR/config"
J1_CONFIG_DIR="$CONFIG_DIR/snapmaker_j1"
IMAGE_DIR="$J1_CONFIG_DIR/images"
GCODE_DIR="$DATA_DIR/gcodes/snapmaker_j1"
KS_CONF="$CONFIG_DIR/KlipperScreen.conf"
MOONRAKER_CONF="$CONFIG_DIR/moonraker.conf"
APK=""
IMAGES=""

while [ $# -gt 0 ]; do
    case "$1" in
        --apk) APK="$2"; shift 2 ;;
        --images) IMAGES="$2"; shift 2 ;;
        *) echo "Unknown option $1"; exit 1 ;;
    esac
done

for dir in "$KLIPPER_DIR" "$KS_DIR" "$CONFIG_DIR"; do
    if [ ! -d "$dir" ]; then
        echo "$dir not found (set KLIPPER_DIR, KS_DIR or DATA_DIR)"
        exit 1
    fi
done

# Keep a linked path out of the git status of Klipper or KlipperScreen,
# so that their update manager entries do not report local changes
exclude() {
    local repo="$1" path="$2"
    local file="$repo/.git/info/exclude"
    if [ -d "$repo/.git" ] && ! grep -qxF "$path" "$file" 2>/dev/null; then
        mkdir -p "$repo/.git/info"
        echo "$path" >> "$file"
    fi
}

# Klipper host modules
for module in "$REPO_DIR"/klippy/extras/*.py; do
    name="$(basename "$module")"
    ln -sfn "$module" "$KLIPPER_DIR/klippy/extras/$name"
    exclude "$KLIPPER_DIR" "klippy/extras/$name"
done

# Printer configuration (included from printer.cfg; SAVE_CONFIG results
# stay in printer.cfg)
mkdir -p "$J1_CONFIG_DIR"
for cfg in "$REPO_DIR"/config/*.cfg; do
    ln -sfn "$cfg" "$J1_CONFIG_DIR/$(basename "$cfg")"
done
J1_PRINTER_CFG="snapmaker_j1/printer-snapmaker-j1-2022.cfg"
if [ ! -e "$CONFIG_DIR/printer.cfg" ]; then
    printf '[include %s]\n' "$J1_PRINTER_CFG" > "$CONFIG_DIR/printer.cfg"
elif ! grep -qF "[include $J1_PRINTER_CFG]" "$CONFIG_DIR/printer.cfg"; then
    echo "Add this line to printer.cfg (and remove sections it replaces):"
    echo "  [include $J1_PRINTER_CFG]"
fi

# Moonraker update manager entry for this repository
ln -sfn "$REPO_DIR/moonraker/KlipperSnapmakerJ1.conf" \
    "$J1_CONFIG_DIR/moonraker.conf"
touch "$MOONRAKER_CONF"
if ! grep -qF "[include snapmaker_j1/moonraker.conf]" "$MOONRAKER_CONF"
then
    printf '\n[include snapmaker_j1/moonraker.conf]\n' >> "$MOONRAKER_CONF"
fi

# KlipperScreen add-on (calibration menu)
mkdir -p "$KS_DIR/addons"
ln -sfn "$REPO_DIR/klipperscreen/snapmaker_j1" "$KS_DIR/addons/snapmaker_j1"
exclude "$KS_DIR" "addons/snapmaker_j1"

# Theme after the stock display; the icons are the KlipperScreen
# material-dark set recolored to the J1 palette
THEME_SRC="$REPO_DIR/klipperscreen/snapmaker_j1/theme"
THEME_DIR="$KS_DIR/styles/snapmaker-j1"
mkdir -p "$THEME_DIR"
ln -sfn "$THEME_SRC/style.css" "$THEME_DIR/style.css"
ln -sfn "$THEME_SRC/style.conf" "$THEME_DIR/style.conf"
python3 "$THEME_SRC/make_icons.py" "$KS_DIR/styles/material-dark/images" \
    "$THEME_DIR/images"
exclude "$KS_DIR" "styles/snapmaker-j1"

# Pictures and test prints of the calibration menu
mkdir -p "$IMAGE_DIR" "$GCODE_DIR"
if [ -n "$IMAGES" ]; then
    cp "$IMAGES"/*.gif "$IMAGES"/*.png "$IMAGE_DIR"/ 2>/dev/null || true
fi
if [ -n "$APK" ]; then
    python3 "$REPO_DIR/scripts/snapmaker_j1_extract_assets.py" "$APK" \
        --images "$IMAGE_DIR" --gcodes "$GCODE_DIR" --skip-existing
fi

# KlipperScreen configuration: enable add-ons, select the theme and
# include the J1 menu
touch "$KS_CONF"
SAVED_MARK="#~# --- Do not edit below this line"

# Add lines to the user part of KlipperScreen.conf; KlipperScreen ignores
# anything after the block it saves from its settings menu
add_user_lines() {
    python3 - "$KS_CONF" "$1" "$SAVED_MARK" <<'PY'
import sys
path, text, mark = sys.argv[1:]
content = open(path).read()
i = content.find("\n" + mark)
if i < 0:
    content = content.rstrip("\n") + "\n\n" + text + "\n"
else:
    content = content[:i].rstrip("\n") + "\n\n" + text + "\n" + content[i:]
open(path, "w").write(content)
PY
}

if ! grep -q "^\[main\]" "$KS_CONF"; then
    add_user_lines "[main]"
fi
if ! grep -q "^enable_addons" "$KS_CONF"; then
    sed -i '/^\[main\]/a enable_addons: True' "$KS_CONF"
fi
if grep -q "^theme:" "$KS_CONF"; then
    sed -i 's/^theme:.*/theme: snapmaker-j1/' "$KS_CONF"
else
    sed -i '/^\[main\]/a theme: snapmaker-j1' "$KS_CONF"
fi
# A theme chosen in the settings menu is saved at the end and wins
sed -i 's/^#~# theme = .*/#~# theme = snapmaker-j1/' "$KS_CONF"
J1_MENU="$REPO_DIR/klipperscreen/snapmaker_j1/snapmaker_j1.conf"
if ! grep -qF "[include $J1_MENU]" "$KS_CONF"; then
    add_user_lines "[include $J1_MENU]"
fi

echo "Installed. Restart the services:"
echo "  sudo systemctl restart moonraker klipper KlipperScreen"
