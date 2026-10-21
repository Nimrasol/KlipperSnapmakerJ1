#!/usr/bin/env python3
# Package a Klipper build for the Snapmaker J1 factory bootloader
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import sys, struct, argparse, time

# The J1 main controller update image ("mc.bin") is a 256 byte header
# (of which the first 101 bytes are used) followed by the raw
# application image.  The factory bootloader stores the header at
# 0x080FD000 and only starts an application whose checksum matches.
HEADER_FORMAT = "<21sBHBHH32s20sHIIIBBI"
HEADER_PAD = 256
FILE_FLAG = b"snapmaker update.bin"
IMAGE_TYPE_MC = 3
STATUS_NONE = 0xAA00
STATUS_APP_NORMAL = 0xAA05
# Port and SACP id the bootloader requests the image from: the display is
# on the second port (USART2), as the stock firmware stores it
BOOT_PORT_HMI = 1
SACP_ID_HMI = 2
APP_START = 0x08002800
APP_LIMIT = 0x080FD000
# The display's USB update package ("update.bin") holds a 75 byte table
# of contents followed by the module images
UPDATE_TOC_SIZE = 75
UPDATE_TOC_COUNT_OFFSET = 38
UPDATE_ENTRY_MC = 0

def checksum(data):
    total = 0
    for i in range(0, len(data) - 1, 2):
        total += (data[i] << 8) | data[i + 1]
    if len(data) & 1:
        total += data[-1]
    return ~total & 0xffffffff

def build_header(app, version, status):
    if len(app) > APP_LIMIT - APP_START:
        raise SystemExit("Application image is too large")
    pack_time = time.strftime("%Y.%m.%d:%H:%M:%S").encode()
    fields = [FILE_FLAG, 1, IMAGE_TYPE_MC, 1, 0, 0,
              version.encode()[:31], pack_time[:20], status, len(app),
              checksum(app), APP_START, BOOT_PORT_HMI, SACP_ID_HMI, 0]
    hdr = struct.pack(HEADER_FORMAT, *fields)
    hdr = hdr[:-4] + struct.pack("<I", checksum(hdr[:-4]))
    return hdr

def build_mc_bin(app, version):
    hdr = build_header(app, version, STATUS_NONE)
    return hdr + b"\0" * (HEADER_PAD - len(hdr)) + app

def build_update_bin(mc_bin, version):
    toc = bytearray(UPDATE_TOC_SIZE)
    toc[2:34] = version.encode()[:32].ljust(32, b" ")
    toc[UPDATE_TOC_COUNT_OFFSET] = 1
    struct.pack_into(">BII", toc, UPDATE_TOC_COUNT_OFFSET + 1,
                     UPDATE_ENTRY_MC, UPDATE_TOC_SIZE, len(mc_bin))
    return bytes(toc) + mc_bin

def main():
    parser = argparse.ArgumentParser(
        description="Package out/klipper.bin for the Snapmaker J1")
    parser.add_argument("klipper_bin", help="path to out/klipper.bin")
    parser.add_argument("--version", default="Klipper",
                        help="version string stored in the image header")
    parser.add_argument("--mc-bin", help="write a display update image")
    parser.add_argument("--update-bin",
                        help="write a USB update package for the display")
    parser.add_argument("--swd-header",
                        help="write the boot header to flash at 0x080FD000"
                        " when programming the application via SWD")
    args = parser.parse_args()
    app = open(args.klipper_bin, "rb").read()
    if not (args.mc_bin or args.update_bin or args.swd_header):
        parser.error("no output requested")
    mc_bin = build_mc_bin(app, args.version)
    if args.mc_bin:
        open(args.mc_bin, "wb").write(mc_bin)
    if args.update_bin:
        open(args.update_bin, "wb").write(build_update_bin(mc_bin,
                                                           args.version))
    if args.swd_header:
        open(args.swd_header, "wb").write(
            build_header(app, args.version, STATUS_APP_NORMAL))
    sys.stdout.write("Application: %d bytes, checksum 0x%08x\n"
                     % (len(app), checksum(app)))

if __name__ == '__main__':
    main()
