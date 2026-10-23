#!/usr/bin/env python3
# Install a main controller image on the Snapmaker J1 through its factory
# bootloader, from the display module (the Klipper host)
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import sys, time, struct, argparse
import serial

# The stock display updates the main controller over the same UART that
# Klipper uses (USART2 of the main controller, /dev/ttyMSM1 of the display)
# with SACP frames of command set 0xad:
#   0x01 display -> controller: 256 byte image header.  The stock firmware
#        or the factory bootloader (V1.0.3, during the first seconds after
#        a reset or while it waits for an update) checks it, stores it at
#        0x080FD000 and starts the update.
#   0x02 bootloader -> display: request image bytes (offset, max length);
#        the answer carries the bytes.  The bootloader erases and writes
#        only the application pages given by the checked header, never
#        its own pages (0x08000000-0x080027FF).
#   0x03 bootloader -> display: result, then it starts the new application
#        (or waits for another update if the checksum does not match).
# Klipper resets into the bootloader on the serial bootloader request, the
# stock firmware on M1999.  The bootloader also listens on the USB port of
# the main controller (USART1 through a CH340), so the script works there
# as well, also when the firmware does not answer: switch the printer off
# and on while the script waits.
SOF = b"\xaa\x55"
SACP_VERSION = 1
ID_CONTROLLER = 1
ID_HMI = 2
ATTR_REQ = 0
ATTR_ACK = 1
CMD_SET_UPDATE = 0xad
CMD_START = 0x01
CMD_PACKAGE = 0x02
CMD_RESULT = 0x03

BOOT_BAUD = 115200
KLIPPER_BOOTLOADER_REQUEST = b"~ \x1c Request Serial Bootloader!! ~"
STOCK_RESET = b"M1999\n"

# Image header ("mc.bin"), as checked by the bootloader
HEADER_SIZE = 256
HEADER_FORMAT = "<21sBHBHH32s20sHIIIBBI"
HEADER_USED = struct.calcsize(HEADER_FORMAT)
FILE_FLAG = b"snapmaker update.bin"
IMAGE_TYPE_MC = 3
BOOTLOADER_END = 0x08002800
APP_LIMIT = 0x080FD000
APP_PAGE = 2048
RAM_START, RAM_END = 0x20000000, 0x20018000
# USB update package of the display ("update.bin")
UPDATE_TOC_SIZE = 75
UPDATE_TOC_COUNT_OFFSET = 38
UPDATE_ENTRY_MC = 0

START_RESULTS = {
    1: "the header is too short",
    4: "the start address or length is out of range",
    5: "the image is not for the main controller",
    6: "the header checksum is wrong",
}

class FlashError(Exception):
    pass

######################################################################
# Image
######################################################################

def checksum32(data):
    total = 0
    for i in range(0, len(data) - 1, 2):
        total += (data[i] << 8) | data[i + 1]
    if len(data) & 1:
        total += data[-1]
    return ~total & 0xffffffff

def extract_mc_bin(data):
    # A display update package holds the main controller image as entry 0
    if data[:len(FILE_FLAG)] == FILE_FLAG:
        return data
    count = data[UPDATE_TOC_COUNT_OFFSET] if len(data) > 75 else 0
    for i in range(count):
        entry, offset, length = struct.unpack_from(
            ">BII", data, UPDATE_TOC_COUNT_OFFSET + 1 + 9 * i)
        if entry == UPDATE_ENTRY_MC:
            return data[offset:offset + length]
    raise FlashError("Not a main controller image (mc.bin) or update"
                     " package (update.bin)")

def check_image(data):
    # The checks of the factory bootloader, plus the application checksum
    # and vector table, so that only a complete image is sent
    if len(data) < HEADER_SIZE:
        raise FlashError("Image is too short")
    hdr = data[:HEADER_USED]
    (flag, pack_version, image_type, force, start_id, end_id, version,
     pack_time, status, app_length, app_checksum, app_start, port,
     receiver, hdr_checksum) = struct.unpack(HEADER_FORMAT, hdr)
    if flag[:len(FILE_FLAG)] != FILE_FLAG:
        raise FlashError("Missing image header (\"snapmaker update.bin\")")
    if checksum32(hdr[:-4]) != hdr_checksum:
        raise FlashError("Image header checksum is wrong")
    if image_type != IMAGE_TYPE_MC:
        raise FlashError("Image type %d is not a main controller image"
                         % (image_type,))
    if app_start % APP_PAGE or app_start < BOOTLOADER_END:
        raise FlashError("Start address 0x%08x would overlap the"
                         " bootloader" % (app_start,))
    if not app_length or app_start + app_length > APP_LIMIT:
        raise FlashError("Application length %d is out of range"
                         % (app_length,))
    app = data[HEADER_SIZE:HEADER_SIZE + app_length]
    if len(app) != app_length:
        raise FlashError("Image is truncated (%d of %d bytes)"
                         % (len(app), app_length))
    if checksum32(app) != app_checksum:
        raise FlashError("Application checksum is wrong")
    sp, reset = struct.unpack_from("<II", app, 0)
    if (not RAM_START < sp <= RAM_END or not reset & 1
        or not app_start <= reset & ~1 < app_start + app_length):
        raise FlashError("Application has no valid vector table")
    return {'header': data[:HEADER_SIZE], 'app': app, 'start': app_start,
            'version': version.split(b"\0")[0].decode('ascii', 'replace'),
            'checksum': app_checksum}

######################################################################
# SACP
######################################################################

def crc8(data):
    crc = 0
    for b in data:
        for j in range(8):
            bit = (b >> (7 - j)) & 1
            c07 = (crc >> 7) & 1
            crc = (crc << 1) & 0xff
            if c07 ^ bit:
                crc ^= 0x07
    return crc

def checksum16(data):
    total = 0
    for i in range(0, len(data) - 1, 2):
        total += (data[i] << 8) | data[i + 1]
    if len(data) & 1:
        total += data[-1]
    while total > 0xffff:
        total = (total >> 16) + (total & 0xffff)
    return ~total & 0xffff

def build_frame(receiver, attr, sequence, command_set, command_id, payload):
    head = SOF + struct.pack("<HBB", len(payload) + 8, SACP_VERSION,
                             receiver)
    body = struct.pack("<BBHBB", ID_HMI, attr, sequence, command_set,
                       command_id) + payload
    return (head + bytes([crc8(head)]) + body
            + struct.pack("<H", checksum16(body)))

class Frame:
    def __init__(self, raw):
        (self.receiver,) = struct.unpack_from("<B", raw, 5)
        (self.sender, self.attr, self.sequence, self.command_set,
         self.command_id) = struct.unpack_from("<BBHBB", raw, 7)
        self.payload = raw[13:-2]

class FrameParser:
    # Splits the received bytes into SACP frames and log text (the
    # bootloader prints its progress as plain text on the same port)
    def __init__(self):
        self.buf = b""
        self.text = b""
    def feed(self, data):
        self.buf += data
        frames = []
        while True:
            pos = self.buf.find(SOF)
            if pos < 0:
                keep = 1 if self.buf.endswith(SOF[:1]) else 0
                self.text += self.buf[:len(self.buf) - keep]
                self.buf = self.buf[len(self.buf) - keep:]
                break
            self.text += self.buf[:pos]
            self.buf = self.buf[pos:]
            if len(self.buf) < 7:
                break
            if crc8(self.buf[:6]) != self.buf[6]:
                self.text += self.buf[:1]
                self.buf = self.buf[1:]
                continue
            total = struct.unpack_from("<H", self.buf, 2)[0] + 7
            if len(self.buf) < total:
                break
            raw, self.buf = self.buf[:total], self.buf[total:]
            body = raw[7:-2]
            if checksum16(body) == struct.unpack_from("<H", raw, total - 2)[0]:
                frames.append(Frame(raw))
        return frames
    def lines(self):
        *done, self.text = self.text.split(b"\n")
        return [l.strip(b"\r\0").decode('ascii', 'replace') for l in done
                if l.strip(b"\r\0")]

######################################################################
# Update
######################################################################

class Flasher:
    def __init__(self, port, image, verbose=False, reopen=None):
        self.port = port
        self.reopen = reopen
        self.image = image
        self.verbose = verbose
        self.parser = FrameParser()
        self.sequence = 0
        self.last_offset = None
        self.pending = []
    def log(self, msg):
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    def receive(self):
        if self.pending:
            frames, self.pending = self.pending, []
            return frames
        frames = self.parser.feed(self.port.read(4096))
        for line in self.parser.lines():
            if self.verbose:
                self.log("  controller: %s" % (line,))
        return [f for f in frames if f.command_set == CMD_SET_UPDATE
                and f.sender == ID_CONTROLLER]
    def send(self, attr, sequence, command_id, payload):
        self.port.write(build_frame(ID_CONTROLLER, attr, sequence,
                                    CMD_SET_UPDATE, command_id, payload))
    def start(self, timeout):
        # Repeat the header until the firmware or the bootloader accepts it
        payload = struct.pack("<H", HEADER_SIZE) + self.image['header']
        end = time.time() + timeout
        next_send = 0.
        while time.time() < end:
            try:
                if time.time() >= next_send:
                    self.sequence = (self.sequence + 1) & 0xffff
                    self.send(ATTR_REQ, self.sequence, CMD_START, payload)
                    next_send = time.time() + 0.25
                frames = self.receive()
            except (serial.SerialException, OSError):
                # A USB serial adapter powered by the printer disappears
                # while it is switched off
                if self.reopen is None:
                    raise
                self.log("Port lost, waiting for it...")
                self.port = self.wait_port(end)
                self.parser = FrameParser()
                continue
            for i, frame in enumerate(frames):
                if frame.command_id == CMD_START and frame.payload:
                    result = frame.payload[0]
                    if result:
                        raise FlashError(
                            "The main controller rejected the image: %s"
                            % (START_RESULTS.get(result, "error %d"
                                                 % (result,)),))
                    self.pending = frames[i + 1:]
                    return
                if frame.command_id in (CMD_PACKAGE, CMD_RESULT):
                    # Accepted, but the answer got lost
                    self.pending = frames[i:]
                    return
        raise FlashError(
            "No answer from the main controller - check that Klipper is"
            " stopped, the port is right and the printer is switched on")
    def wait_port(self, end):
        try:
            self.port.close()
        except (serial.SerialException, OSError):
            pass
        while time.time() < end:
            time.sleep(0.5)
            try:
                return self.reopen()
            except FlashError:
                pass
        raise FlashError("The port did not come back")
    def handle(self, frame):
        # (the bootloader does not set the attribute of its answers)
        if frame.command_id == CMD_PACKAGE:
            offset, max_len = struct.unpack_from("<IH", frame.payload)
            app = self.image['app']
            if offset >= len(app):
                self.send(ATTR_ACK, frame.sequence, CMD_PACKAGE, b"\x01")
                return None
            chunk = app[offset:offset + max_len]
            self.send(ATTR_ACK, frame.sequence, CMD_PACKAGE,
                      struct.pack("<BIH", 0, offset, len(chunk)) + chunk)
            if offset != self.last_offset:
                self.last_offset = offset
                done = offset + len(chunk)
                self.log("  %3d%%  %d of %d bytes"
                         % (done * 100 // len(app), done, len(app)))
            return None
        if frame.command_id == CMD_RESULT:
            self.send(ATTR_ACK, frame.sequence, CMD_RESULT, b"\x00")
            return frame.payload[0] if frame.payload else 1
        return None
    def transfer(self, timeout):
        # The bootloader erases the old application first, then requests
        # the image piece by piece and reports the result
        end = time.time() + timeout
        while time.time() < end:
            for frame in self.receive():
                result = self.handle(frame)
                if result is not None:
                    return result
                end = time.time() + timeout
        raise FlashError(
            "The bootloader stopped requesting data.  The main controller"
            " waits in its bootloader; run this script again.")

def open_port(device, baud):
    try:
        return serial.Serial(device, baud, timeout=0.05, exclusive=True)
    except (serial.SerialException, OSError) as e:
        raise FlashError("Unable to open %s (%s) - stop Klipper first"
                         % (device, e))

def main():
    parser = argparse.ArgumentParser(
        description="Install a main controller image (mc.bin or the"
        " display's update.bin) on the Snapmaker J1 through its factory"
        " bootloader.  Stop Klipper first.")
    parser.add_argument("image", help="firmware/out/mc.bin, a stock mc.bin"
                        " or update.bin")
    parser.add_argument("-d", "--device", default="/dev/ttyMSM1",
                        help="serial port of the main controller: the"
                        " display link (default /dev/ttyMSM1) or its USB"
                        " port (for example /dev/ttyUSB0 on another"
                        " computer)")
    parser.add_argument("-b", "--baud", type=int, default=230400,
                        help="baud rate of the running Klipper firmware,"
                        " used for the bootloader request (default 230400)")
    parser.add_argument("-w", "--wait", type=float, default=15.,
                        help="seconds to wait for the bootloader (switch"
                        " the printer off and on meanwhile if the firmware"
                        " does not answer; default 15)")
    parser.add_argument("--check", action="store_true",
                        help="only check the image")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show the bootloader messages")
    args = parser.parse_args()
    try:
        image = check_image(extract_mc_bin(open(args.image, "rb").read()))
        sys.stdout.write(
            "Image %s: %d bytes at 0x%08x, checksum 0x%08x\n"
            % (image['version'] or "?", len(image['app']), image['start'],
               image['checksum']))
        if args.check:
            return
        port = open_port(args.device, args.baud)
        # Klipper resets into the bootloader on its request, the stock
        # firmware on M1999 (USB port) or accepts the header itself
        # (display port); the bootloader ignores both
        port.write(KLIPPER_BOOTLOADER_REQUEST)
        port.flush()
        time.sleep(0.1)
        port.baudrate = BOOT_BAUD
        port.write(STOCK_RESET * 3)
        port.flush()
        time.sleep(0.1)
        port.reset_input_buffer()
        flasher = Flasher(port, image, args.verbose,
                          reopen=lambda: open_port(args.device, BOOT_BAUD))
        flasher.log("Waiting for the bootloader...")
        flasher.start(timeout=args.wait)
        flasher.log("Image accepted, erasing and writing...")
        result = flasher.transfer(timeout=60.)
        if result:
            raise FlashError(
                "The bootloader reports a failed update (%d).  The main"
                " controller waits in its bootloader; run this script"
                " again." % (result,))
        flasher.log("Update complete, the main controller starts the new"
                    " firmware.  Start Klipper again.")
    except FlashError as e:
        sys.stderr.write("Error: %s\n" % (e,))
        sys.exit(1)

if __name__ == '__main__':
    main()
