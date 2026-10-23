#!/bin/bash
# Build the Snapmaker J1 main controller firmware
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Usage: firmware/build.sh
#
# The firmware is built from the installed Klipper (KLIPPER_DIR, default
# ~/klipper) with the GD32F305 patch applied to a copy, so the Klipper
# checkout itself stays unmodified.  The results are written to
# firmware/out: klipper.bin, mc.bin (scripts/snapmaker_j1_flash.py),
# update.bin (stock display USB update) and boot-header.bin (SWD, see
# docs/Snapmaker_J1.md).
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
# The copy of Klipper lives outside this repository: inside a git work
# tree "git apply" silently skips the paths outside the current directory
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
OUT_DIR="$REPO_DIR/firmware/out"
# Klipper version the patch was made for and this release is tested with
TESTED=$(awk '$1 == "klipper" {print $3 " (" $2 ")"}' \
    "$REPO_DIR/versions.conf")
INSTALLED=$(git -C "$KLIPPER_DIR" describe --tags --always)

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
git -C "$KLIPPER_DIR" archive HEAD | tar -x -C "$BUILD_DIR"
cd "$BUILD_DIR"
if ! git apply --verbose "$REPO_DIR/firmware/klipper-gd32f305-snapmaker.patch" \
        2> patch.log || ! grep -q "src/stm32/snapmaker_boot.c" patch.log; then
    echo "The patch does not apply to Klipper $INSTALLED; it was made"
    echo "for Klipper $TESTED (versions.conf)."
    exit 1
fi
cp "$REPO_DIR/firmware/snapmaker-j1.config" .config
make olddefconfig > /dev/null
# A missing option falls back silently to another chip or offset
for opt in CONFIG_MACH_GD32F305=y CONFIG_STM32_FLASH_START_2800=y \
        CONFIG_FLASH_APPLICATION_ADDRESS=0x8002800 \
        CONFIG_CLOCK_FREQ=120000000 CONFIG_STM32_SERIAL_USART2_ALT_PD6_PD5=y \
        CONFIG_STM32_SNAPMAKER_BOOTLOADER=y \
        'CONFIG_INITIAL_PINS="PD4,PC10,!PA10,!PA9,!PC11,!PE14,!PE13"'; do
    if ! grep -qxF "$opt" .config; then
        echo "Build configuration lacks $opt - the firmware would not work"
        exit 1
    fi
done
make -j"$(nproc)"
cp out/klipper.bin "$OUT_DIR/"
python3 "$REPO_DIR/scripts/snapmaker_j1_package.py" out/klipper.bin \
    --update-bin "$OUT_DIR/update.bin" --mc-bin "$OUT_DIR/mc.bin" \
    --swd-header "$OUT_DIR/boot-header.bin"
echo "Firmware for Klipper $INSTALLED in $OUT_DIR"
echo "Install it with Klipper stopped:"
echo "  ~/klippy-env/bin/python $REPO_DIR/scripts/snapmaker_j1_flash.py $OUT_DIR/mc.bin"
case "$TESTED" in
    "$INSTALLED "*) ;;
    *) echo "Note: this release is tested with Klipper $TESTED" ;;
esac
