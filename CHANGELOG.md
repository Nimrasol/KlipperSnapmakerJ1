# Changelog

Versions follow [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`,
released as git tags `vX.Y.Z`.  The update manager shows this version.

- **MAJOR:** changes that need action from the user, for example a new
  main controller firmware, a new display system or a configuration that
  has to be adapted by hand.
- **MINOR:** new functions, and moving to newer tested versions of
  Klipper, Moonraker or KlipperScreen (`versions.conf`).
- **PATCH:** fixes.

## v1.1.0 (2026-10-30)

- **Installation from a USB stick** on the Snapmaker touch screen, with
  [KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os):
  the installation package installs the display system and, on the
  first start, the Klipper firmware of the main controller.
- **Back to the stock firmware** from the touch screen: More → System,
  at the end of the page, **Stock Firmware** installs the official
  Snapmaker update package and the Snapmaker system from a USB stick
  (with [KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os)).
- **Menus:** the main menu in the order of a print (Print, Temperature,
  Extrude, Move, Calibration, More); More in rows for printing,
  settings and maintenance; WLAN and Network Name in one Network menu.
- **Move:** Z- at the top, Z+ below it.
- **Documentation:** both ways, stock firmware → Klipper and Klipper →
  stock firmware, in the installation, with download buttons and a
  warning to calibrate before the first print; new pictures of the
  changed screens.

## v1.0.1 (2026-10-27)

- **Documentation:** the user manual starts with the first start: connect
  the WLAN and calibrate before the first print.  The clock only runs
  correctly with the WLAN connected.
- With [KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os):
  the update manager checks for updates as soon as the WLAN is connected,
  instead of showing no versions after a start without network.

## v1.0.0 (2026-10-27)

First release tested on the printer: KlipperSnapmakerJ1 runs the J1 with
Klipper, Moonraker, KlipperScreen and Mainsail on the display module
([KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os)).

Tested with Klipper v0.13.0-816-gee2c6fb6, Moonraker v0.11.0-4-gb559b9a
and KlipperScreen v0.4.7-198-g911c75b (`versions.conf`).

- **Printing:** IDEX full control, duplication, mirror and backup mode
  from the print file; tool changes with parking; pause and resume with
  parking, priming and wiping of both toolheads; paused prints cool down
  after the pause standby time; clean up after a completed print like
  the stock firmware.
- **Print start:** check of the nozzle diameters against the file, with
  the stock dialog.
- **Calibration menu:** heated bed leveling, Z offset, XY offset
  (assisted and manual with a test print), offset check, vibration
  compensation, PID auto tune and build plate thickness, with the
  pictures and animations of the stock display and the live height
  indicator.  The results are stored at once, without a restart.
- **Probing:** like the stock firmware, guarded by StallGuard crash
  detection.
- **Filament:** motion sensors on both toolheads, runout and change
  dialog, loading and unloading with purging beside the wipers.
- **Power loss recovery** of the interrupted print.
- **Heaters:** limits and protections of the stock firmware; a missing
  hotend only blocks its own heater; PID defaults measured on a J1.
- **Touch screen:** theme after the stock display, Light panel (case
  light, dimming, screen off after 15 minutes), fans, limits, network
  name, clock and time zone.
- **Main controller firmware:** Klipper on the GD32F305, installed from
  the display module through the factory bootloader.
- **Installation:** the calibration pictures and test prints are part of
  the repository; nothing is taken from the printer.
- **Documentation:** user manual with screenshots, technical manual.

## v0.1.0 (2026-10-20)

First version, tested in simulation only.
