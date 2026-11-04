# Changelog

Versions follow [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`,
released as git tags `vX.Y.Z`.  The update manager shows this version.

- **MAJOR:** changes that need action from the user, for example a new
  main controller firmware, a new display system or a configuration that
  has to be adapted by hand.
- **MINOR:** new functions, and moving to newer tested versions of
  Klipper, Moonraker or KlipperScreen (`versions.conf`).
- **PATCH:** fixes.

## Unreleased

- **Saving the Z offset works:** **Save** next to the Z offset in Mainsail
  (`Z_OFFSET_APPLY_ENDSTOP`, `Z_OFFSET_APPLY_PROBE`) failed with a
  conflict in `printer.cfg`.  It now stores the offset in the Z origin, as
  the calibration does; during a print when the print ends.

## v1.3.0 (2026-11-04)

- **Board revision 1:** Klipper detects the main board revision at the
  start and sets the revision 1 pins (mains failure input, StallGuard)
  by itself, with one automatic restart; before, it stopped with an
  error on these boards.  Untested on a revision 1 board so far.
- Board revisions after 2 run like revision 2, as in the stock firmware.
- **Print mode on the touch screen:** the print dialog offers IDEX,
  backup, duplication and mirror for every file and moves the print in X
  to where the mode needs it, with the checks of the stock display (one
  toolhead only; duplication narrower than 160 mm, mirror than 150 mm).
  The purge line of the start G-code stays in place and does not count.
  In Mainsail and Fluidd the macro `SNAPMAKER_PRINT_MODE` offers the same
  choice, with a list of the newest files to choose from; Mainsail gets a
  panel **Snapmaker J1** with it at the top of the dashboard (unless its
  macros are set up already).  The `M605` of the file then does not
  change the chosen mode.
- **Retraction warning:** a print of a file that retracts more than 2 mm
  (OrcaSlicer: printer or filament profile) asks first, as on the stock
  display: a dialog of its own after the nozzle diameter check, for
  every print start (touch screen, web interface, slicer).
- **Touch screen after an update:** KlipperScreen restarts by itself once
  the update changed its add-on and the printer is idle, so new functions
  appear without restarting the printer.  This works from the next update
  on: the update that brings it still needs one restart of the printer.
- **Power loss recovery** also for a print file in a subfolder, such as
  the moved copy of a print mode ("Unable to open file" before).

## v1.2.0 (2026-10-31)

- **Display wakes up again on touch** after the screen saver switched it
  off during a print with tool changes (the print status page covered
  the screen saver and took the touch).
- **Updates only with releases:** the update manager offers new versions
  of KlipperSnapmakerJ1 when a release is published, no longer every
  change in between.
- **Update notice:** the touch screen asks once per new release whether
  to update (**Update** / **Later**), not while printing.
- **Release candidates:** a switch at the end of the Update menu also
  offers test versions (`vX.Y.Z-rc.N`) to users who help testing.

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
