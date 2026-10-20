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
# firmware/out: klipper.bin, update.bin (stock display USB update),
# mc.bin and boot-header.bin (SWD, see docs/Snapmaker_J1.md).
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
KLIPPER_DIR="${KLIPPER_DIR:-$HOME/klipper}"
BUILD_DIR="$REPO_DIR/firmware/build"
OUT_DIR="$REPO_DIR/firmware/out"
# Klipper version the patch was made for and this release is tested with
TESTED=$(awk '$1 == "klipper" {print $3 " (" $2 ")"}' \
    "$REPO_DIR/versions.conf")
INSTALLED=$(git -C "$KLIPPER_DIR" describe --tags --always)

rm -rf "$BUILD_DIR" "$OUT_DIR"
mkdir -p "$BUILD_DIR" "$OUT_DIR"
git -C "$KLIPPER_DIR" archive HEAD | tar -x -C "$BUILD_DIR"
cd "$BUILD_DIR"
if ! git apply "$REPO_DIR/firmware/klipper-gd32f305-snapmaker.patch"; then
    echo "The patch does not apply to Klipper $INSTALLED; it was made"
    echo "for Klipper $TESTED (versions.conf)."
    exit 1
fi
cp "$REPO_DIR/firmware/snapmaker-j1.config" .config
make olddefconfig > /dev/null
make -j"$(nproc)"
cp out/klipper.bin "$OUT_DIR/"
python3 "$REPO_DIR/scripts/snapmaker_j1_package.py" out/klipper.bin \
    --update-bin "$OUT_DIR/update.bin" --mc-bin "$OUT_DIR/mc.bin" \
    --swd-header "$OUT_DIR/boot-header.bin"
echo "Firmware for Klipper $INSTALLED in $OUT_DIR"
case "$TESTED" in
    "$INSTALLED "*) ;;
    *) echo "Note: this release is tested with Klipper $TESTED" ;;
esac
