#!/usr/bin/env python3
# Return a Snapmaker J1 running KlipperSnapmakerJ1-os to the stock firmware
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Everything comes from a USB stick, the contents of the zip archive of a
# KlipperSnapmakerJ1-os release (built by stock/build.sh there):
#   J1_V*.bin        the official Snapmaker update package, for the stock
#                    main controller firmware
#   stock-restore/   the Snapmaker system of the display module, without
#                    personal data: boot.img (boot partition),
#                    userdata.img.gz and userdata-footer.bin (Android data),
#                    cache.img.gz, and manifest (sha256 of each file)
#
#   1. The main controller gets the stock firmware of the package
#      (snapmaker_j1_flash.py, through the factory bootloader).
#   2. The next start runs the maintenance system of KlipperSnapmakerJ1-os
#      (label "maint" of extlinux.conf on the cache partition, request
#      maint/request = restore).  It writes the Snapmaker system while
#      neither Android nor Linux runs; the display then starts it.
#
#   sudo snapmaker_j1_stock.py scan             (JSON: sticks, packages,
#                                                system)
#   sudo snapmaker_j1_stock.py check PACKAGE    (all checks, no changes)
#   sudo snapmaker_j1_stock.py restore PACKAGE
#
# "restore" stops KlipperScreen, Klipper and Moonraker and shows its
# progress on the console of the display.  The display module is changed
# only by the maintenance system, after it checked the files again.
import argparse, hashlib, json, os, struct, subprocess, sys, time, traceback

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import snapmaker_j1_flash as flash

PARTLABEL = "/dev/disk/by-partlabel/"
USB_MOUNT = "/run/snapmaker-j1/usb"
CACHE_MOUNT = "/run/snapmaker-j1/cache"
SYSTEM_DIR = "stock-restore"
SYSTEM_FILES = ["boot.img", "userdata.img.gz", "userdata-footer.bin",
                "cache.img.gz"]
PACKAGE_NAME_OFFSET, PACKAGE_NAME_SIZE = 2, 36
CONSOLE = "/dev/tty1"
KLIPPY_PYTHON = "/home/pi/klippy-env/bin/python"
SERVICES = ["KlipperScreen", "klipper", "moonraker"]
EXTLINUX = "extlinux/extlinux.conf"
MAINT_LABEL = "maint"
MAINT_FILES = ["maint.cpio.gz", "zImage", "snapmakerj1.dtb"]

class RestoreError(Exception):
    pass

######################################################################
# Checks
######################################################################

def package_info(path):
    # Official update package: header size, name, then the table of
    # contents with the main controller image (entry 0) and the application
    # (entry 3)
    with open(path, "rb") as f:
        data = f.read()
    try:
        image = flash.check_image(flash.extract_mc_bin(data))
    except flash.FlashError as e:
        raise RestoreError("%s: %s" % (os.path.basename(path), e))
    name = data[PACKAGE_NAME_OFFSET:PACKAGE_NAME_OFFSET + PACKAGE_NAME_SIZE]
    name = name.split(b"\0")[0].decode("ascii", "replace")
    if not name.startswith("J1_V"):
        raise RestoreError("%s is not a Snapmaker J1 update package"
                           % (os.path.basename(path),))
    return {"path": path, "name": name, "mc_version": image["version"]}

def partition_size(label):
    dev = os.path.realpath(PARTLABEL + label)
    with open("/sys/class/block/%s/size" % (os.path.basename(dev),)) as f:
        return int(f.read()) * 512

def check_boot_image(path):
    # The stock boot image: an Android boot image with the stock kernel
    # (lk2nd is an Android boot image as well, without these arguments)
    with open(path, "rb") as f:
        data = f.read(64 + 512)
    if data[:8] != b"ANDROID!":
        raise RestoreError("%s is not an Android boot image" % (path,))
    kernel_size, = struct.unpack_from("<I", data, 8)
    cmdline = data[64:].split(b"\0")[0]
    if (b"androidboot.hardware=qcom" not in cmdline
            or kernel_size < 4 * 1024 * 1024):
        raise RestoreError("%s is not the stock boot image" % (path,))
    if os.path.getsize(path) > partition_size("boot"):
        raise RestoreError("%s is larger than the boot partition" % (path,))

def read_manifest(system):
    sums = {}
    with open(os.path.join(system, "manifest")) as f:
        for line in f:
            if line.strip():
                digest, name = line.split()
                sums[name.lstrip("*")] = digest
    missing = [n for n in SYSTEM_FILES if n not in sums
               or not os.path.exists(os.path.join(system, n))]
    if missing:
        raise RestoreError("%s/ on the USB stick lacks %s"
                           % (SYSTEM_DIR, ", ".join(missing)))
    return sums

def find_system(stick_dirs):
    for d in stick_dirs:
        system = os.path.join(d, SYSTEM_DIR)
        if os.path.exists(os.path.join(system, "manifest")):
            read_manifest(system)
            check_boot_image(os.path.join(system, "boot.img"))
            return system
    raise RestoreError("No Snapmaker system (%s/) on the USB stick; copy"
                       " the contents of the stock firmware zip archive"
                       " onto it" % (SYSTEM_DIR,))

def verify_system(system):
    for name, digest in read_manifest(system).items():
        h = hashlib.sha256()
        with open(os.path.join(system, name), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != digest:
            raise RestoreError("%s on the USB stick is damaged" % (name,))

def check_maint():
    # The maintenance system on the cache partition
    with mounted_cache(False) as cache:
        conf = open(os.path.join(cache, EXTLINUX)).read()
        if "label %s" % (MAINT_LABEL,) not in conf:
            raise RestoreError("The display system has no maintenance"
                               " system; update KlipperSnapmakerJ1-os")
        for name in MAINT_FILES:
            if not os.path.exists(os.path.join(cache, name)):
                raise RestoreError("%s is missing on the cache partition"
                                   % (name,))

######################################################################
# USB stick and cache partition
######################################################################

def usb_partitions():
    out = subprocess.run(["lsblk", "-J", "-p", "-o",
                          "NAME,FSTYPE,LABEL,TRAN,TYPE,MOUNTPOINT"],
                         capture_output=True, text=True, check=True).stdout
    found = []
    def walk(devs, tran):
        for d in devs:
            t = d.get("tran") or tran
            if t == "usb" and d.get("fstype") == "vfat":
                found.append(d)
            walk(d.get("children") or [], t)
    walk(json.loads(out)["blockdevices"], None)
    return found

def mount_sticks():
    dirs = []
    for i, part in enumerate(usb_partitions()):
        if part.get("mountpoint"):
            dirs.append(part["mountpoint"])
            continue
        target = "%s%d" % (USB_MOUNT, i)
        os.makedirs(target, exist_ok=True)
        if not os.path.ismount(target):
            subprocess.run(["mount", "-o", "ro", part["name"], target],
                           check=True)
        dirs.append(target)
    return dirs

def unmount_sticks():
    for i in range(8):
        target = "%s%d" % (USB_MOUNT, i)
        if os.path.ismount(target):
            subprocess.run(["umount", target])

class mounted_cache:
    def __init__(self, writable):
        self.writable = writable

    def __enter__(self):
        os.makedirs(CACHE_MOUNT, exist_ok=True)
        run(["mount", "-t", "ext2", "-o", "rw" if self.writable else "ro",
             PARTLABEL + "cache", CACHE_MOUNT])
        return CACHE_MOUNT

    def __exit__(self, *exc):
        run(["umount", CACHE_MOUNT])

def find_packages(stick_dirs):
    packages, errors = [], []
    for d in stick_dirs:
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith(".bin") or name.startswith("."):
                continue
            try:
                packages.append(package_info(os.path.join(d, name)))
            except (RestoreError, OSError) as e:
                errors.append(str(e))
    return packages, errors

def scan():
    result = {"sticks": [], "packages": [], "errors": [], "system": None}
    try:
        dirs = mount_sticks()
        result["sticks"] = dirs
        result["packages"], result["errors"] = find_packages(dirs)
        try:
            result["system"] = find_system(dirs)
        except (RestoreError, OSError, ValueError) as e:
            result["errors"].append(str(e))
    except (OSError, subprocess.CalledProcessError) as e:
        result["errors"].append(str(e))
    return result

######################################################################
# Restore
######################################################################

class Console:
    # Progress on the display (the console is turned like the screen).
    # Opened for each message: stopping the getty hangs the terminal up,
    # and a missing console must not stop the restore
    def _write(self, text):
        try:
            with open(CONSOLE, "w") as tty:
                tty.write(text)
        except OSError:
            pass

    def show(self, text):
        print(text, flush=True)
        self._write(text.replace("\n", "\r\n") + "\r\n")

    def clear(self):
        self._write("\033[2J\033[H\033[?25l")

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def request_maintenance():
    # One start of the maintenance system; it sets the default back
    with mounted_cache(True) as cache:
        os.makedirs(os.path.join(cache, "maint"), exist_ok=True)
        with open(os.path.join(cache, "maint", "request"), "w") as f:
            f.write("restore\n")
        path = os.path.join(cache, EXTLINUX)
        lines = open(path).read().splitlines()
        lines = ["default %s" % (MAINT_LABEL,) if l.startswith("default ")
                 else l for l in lines]
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        run(["sync"])

def flash_main_controller(console, package):
    for attempt in range(3):
        result = subprocess.run([KLIPPY_PYTHON,
                                 os.path.join(SCRIPT_DIR,
                                              "snapmaker_j1_flash.py"),
                                 package], capture_output=True, text=True)
        for line in result.stdout.splitlines() + result.stderr.splitlines():
            if "%" not in line:
                console.show("    " + line)
        if result.returncode == 0:
            return
        console.show("    Attempt %d failed" % (attempt + 1,))
        time.sleep(5)
    raise RestoreError("The main controller update failed")

def check(package_path, verify=True):
    # Everything restore needs, without changing anything
    dirs = mount_sticks()
    package = package_info(package_path)
    system = find_system(dirs)
    if verify:
        verify_system(system)
    check_maint()
    for tool in (KLIPPY_PYTHON, "/usr/local/sbin/j1-chvt"):
        if not os.access(tool, os.X_OK):
            raise RestoreError("%s is missing" % (tool,))
    return package, system

def restore(package_path):
    console = Console()
    stopped = False
    try:
        package, system = check(package_path)
        run(["systemctl", "stop"] + SERVICES)
        run(["systemctl", "stop", "getty@tty1"])
        run(["/usr/local/sbin/j1-chvt", "1"])
        stopped = True
        console.clear()
        console.show("\n  Restoring the Snapmaker stock firmware (%s)\n"
                     % (package["name"],))
        console.show("  Do not switch the printer off.  It restarts by"
                     " itself.\n")
        console.show("  Main controller firmware %s"
                     % (package["mc_version"],))
        flash_main_controller(console, package["path"])
        console.show("  Starting the maintenance system: it writes the"
                     " Snapmaker system\n  from the USB stick.  Leave the"
                     " stick plugged in.\n")
        request_maintenance()
        unmount_sticks()
        time.sleep(3)
        run(["systemctl", "reboot"])
    except Exception as e:
        # Any error: Klipper has to come back (the display is unchanged)
        traceback.print_exc()
        console.show("\n  ERROR: %s" % (e,))
        console.show("  Nothing was changed on the display module.")
        unmount_sticks()
        if stopped:
            console.show("  Klipper starts again in 30 seconds.")
            time.sleep(30)
            subprocess.run(["systemctl", "start", "getty@tty1"])
            subprocess.run(["systemctl", "start"] + SERVICES)
        return 1
    return 0

def main():
    parser = argparse.ArgumentParser(
        description="Return the Snapmaker J1 to the stock firmware")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="list USB sticks, packages and system")
    p = sub.add_parser("check", help="run all checks without changes")
    p.add_argument("package", help="official update package (J1_V*.bin)")
    p = sub.add_parser("restore", help="restore the stock firmware")
    p.add_argument("package", help="official update package (J1_V*.bin)")
    args = parser.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run as root (sudo)")
    if args.command == "scan":
        print(json.dumps(scan()))
        return 0
    if args.command == "check":
        try:
            package, system = check(args.package)
        except (RestoreError, OSError, ValueError,
                subprocess.CalledProcessError) as e:
            sys.exit("ERROR: %s" % (e,))
        print("package %s, main controller %s, system %s: all checks"
              " passed" % (package["name"], package["mc_version"], system))
        return 0
    return restore(args.package)

if __name__ == "__main__":
    sys.exit(main())
