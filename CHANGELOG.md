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

- **Elapsed time without pauses:** on the print page of the touch screen,
  **Elapsed** stops while a print is paused (for example after a filament
  runout) and counts on from there when it resumes; before, it kept
  counting through the pause.
- **PID calibration from the temperature page:** the PID button of the
  touch screen did nothing when the heater had a target temperature
  ("Heater is in use"), which is the usual case there.  The calibration
  now takes over a heated heater; it still refuses during a print
  ([#11](https://github.com/Nimrasol/KlipperSnapmakerJ1/issues/11)).
- **Nozzle temperature after a tool change:** heating up from the
  standby temperature, the nozzles overshot by several degrees and took
  a minute or more to come back.  They now heat at full power until
  10C below the target and are regulated from there, as in the stock
  firmware (overshoot below 1C on a J1).  `M109` waits until the target
  is reached, as in the stock firmware, instead of waiting for the
  temperature to settle
  ([#13](https://github.com/Nimrasol/KlipperSnapmakerJ1/issues/13)).
- **Saving the Z offset on the touch screen:** Fine Tuning has a save
  button next to the Z offset; it stores the offset in the Z origin as
  Mainsail's **Save** does, after a confirmation.  The button shows the Z
  offsets saved since the last Z Offset Calibration.  Z- is now above
  Z+.  After a print, the print page offers one **Save Z offset** button
  with the same dialog instead of "Save Z Endstop" and "Save Z Probe",
  which did the same and asked for a Save Config afterwards
  ([#6](https://github.com/Nimrasol/KlipperSnapmakerJ1/issues/6)).
- **Z offset only on a homed printer:** without homing, Klipper took
  every tap on Z+/Z- into the Z offset although nothing moved, and saving
  it shifted the Z origin unnoticed.  `SET_GCODE_OFFSET` now refuses Z
  changes until Z is homed (back to 0 is always possible) and changes
  that would move the bed out of its range; on the touch screen, Z+/Z-
  are disabled until Z is homed.  A start G-code that sets a Z offset
  before `G28` stops with an error now.
- **No false "Save configuration?" dialog:** after saving the Z offset,
  the touch screen asked to save the configuration and restart Klipper,
  although nothing was to save (its message mentioned SAVE_CONFIG).
- **No font size setting on the touch screen:** the larger sizes of
  KlipperScreen made the text barely larger (6% at most) but shrank or
  dropped the icons, and the pages of the J1 are laid out for the default
  size.  The setting is no longer offered; a size chosen before goes back
  to medium with one restart of the screen
  ([#9](https://github.com/Nimrasol/KlipperSnapmakerJ1/issues/9)).
- **WLAN symbol in the title bar:** left of the clock, it shows the
  signal strength of the WLAN in orange bars; without a connection the
  symbol is grey.  A tap shows the network, the signal and the address
  of the web interface (the IP address first, then `<name>.local`, which
  needs mDNS), with a button to the WLAN page
  ([D#8](https://github.com/Nimrasol/KlipperSnapmakerJ1/discussions/8)).
- **Webcam in Mainsail:** a USB webcam (UVC with MJPEG, as most are) in
  the USB port of the display module shows in Mainsail.  The first time a camera is plugged in, the
  touch screen offers to install the streamer (ustreamer, from the
  network); the camera is then added to Mainsail as **J1**.  The stream
  runs while the camera is plugged in (1280 x 720, 15 frames per
  second); while it is unplugged, Mainsail does not show it.
- **Service page:** a button in the action bar of the main menu opens a
  page for service work: a target per heater (kept; 220°C for the
  nozzles, 60°C for the bed) with ON/OFF and the current temperature,
  Load and Unload once a nozzle is hot (also both at once), Nozzle
  Service (both nozzles moved in, about 200 mm apart), Home All,
  Distribute Grease (all axes once over their travel after
  lubricating), Fine Tuning and All Off.  It heats without blocking the
  printer
  ([D#7](https://github.com/Nimrasol/KlipperSnapmakerJ1/discussions/7)).
- **Slower loading:** Load feeds the filament at 240 mm/min as the stock
  refill dialog, on the extrude page too; at 600 mm/min the extruder
  could skip.

## v1.3.1 (2026-11-04)

- **Saving the Z offset works:** **Save** next to the Z offset in Mainsail
  (`Z_OFFSET_APPLY_ENDSTOP`, `Z_OFFSET_APPLY_PROBE`) failed with a
  conflict in `printer.cfg`.  It now stores the offset in the Z origin, as
  the calibration does; during a print when the print ends.
- **Manual:** the print area of the J1 is 324 x 200 mm, the center of the
  bed at X 162, Y 100.

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
