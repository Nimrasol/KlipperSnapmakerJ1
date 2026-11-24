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

## v1.7.0 (2026-11-24)

- **Cancel from a pause:** a print cancelled while paused (for example
  in Mainsail) no longer leaves the touch screen on the extrude page;
  the print page with the result shows again.
- **Cura files start with the left nozzle:** a print starts with the
  left toolhead active, as in the stock firmware.  Cura files heat T0
  but never select a tool; when the right toolhead was active from
  before, the print stopped at once with "Extrude below minimum temp".
- **New home page** (board #21): the service page becomes the home
  page of the touch screen.  One tile per heater with the nozzle
  diameter, the current and the target temperature (a tap shows the
  target on a keypad with the material presets) and ON/OFF.  Three
  temperature gauges (current temperature as an arc, target as a mark;
  the number red while heating, green at the target, blue while
  cooling); a tap on them slides in loading and unloading per nozzle and
  both (a grey button says on a tap that the nozzle has to be on and
  hot).  Home All (asks first), Service (nozzles in for service), Grease
  (distribute it), Light, **Motors Off** (new, asks first) and Heaters
  Off; Print, Move and Calibration below.  The title bar shows the
  printer state: Ready, Heating, what runs (eg Loading T0, Homing) or
  Busy.  The gear in the action bar opens the menu, which now also
  holds Temperature (material presets) and Extrude (any length).
- **Highest targets as the stock firmware:** the keypads and ON set the
  nozzles to at most 300°C and the bed to 100°C (the home page keypad
  took up to 320°C, past the limit of the macros).
- **More → Temperature in the home page style:** the heaters as on the
  home page (orange frame when on, ON/OFF each), Cooldown became
  Heaters Off (all heaters).  During a print ON/OFF is hidden and
  Heaters Off asks first.
- **Faster loading:** Load and unload start once the nozzle is 5°C
  below its target, instead of waiting until the temperature settled
  within 1°C (a minute or more after the overshoot); Load feeds at
  320 mm/min instead of 240 (stock), also in the extrude panel and the
  refill dialog.
- **Move page:** the X, Y and Z fields no longer touch each other, and
  the axis inversion switches are hidden in its settings as intended
  (the patch never applied).
- **WLAN symbol easier to tap:** its tap area in the title bar is larger,
  so the WLAN window opens without hitting the small symbol exactly.
- **Case light during a print:** More → Light has "Dim after
  (Printing)" and "Dim to (Printing)", as the screen settings, for
  example to keep the print lit for the webcam.  The default "As
  without print" keeps the current behavior.  With the same time as the
  screen, the case light dims together with it.
- **Stable Mainsail connection over WLAN:** Wi-Fi power saving is
  switched off.  It delayed packets (pings up to 111ms instead of
  21ms) and Mainsail lost its connection during prints.  The add-on
  sets it once on systems installed before the OS has it.
- **Assisted calibrations stop when a nozzle detects no contact:** the
  XY touch now ends 8mm from the center (was 15mm), a Z touch 3mm below
  the expected bed (was up to 10mm below the travel range), and the
  calibration aborts with "No nozzle contact" instead of pushing the
  nozzle further.  The message points to the manual calibration, which
  coated nozzles need.  After an XY abort the axis is homed again.
- **Fine Tuning during calibration test prints:** the print step of the
  calibration page has a Fine Tuning button (Z offset, speed, flow);
  Back returns to the calibration.
- **Test prints in PETG or ABS:** the Load Filament page of the
  calibration test prints (XY offset, calibration check, vibration)
  offers PLA, PETG and ABS.  The prints are sliced for PLA; PETG prints
  30 °C hotter with the bed at 75 °C, ABS 40 °C hotter at 90 °C
  (`SNAPMAKER_CAL_MATERIAL`).
- **Calibration dialogs** (failed step, quit) show their text centered
  like the other dialogs of the add-on.
- **Power loss recovery while homing:** no state is stored during homing
  and probing moves (the G28 of the start G-code), where Klipper queues
  only a fraction of a second of steps.  Less work in this window; a
  print start once stopped there with "Timer too close" (not
  reproducible, so not proven to be the cause).
- **Print page:** the preview picture of the print is back after a
  pause (it was dropped while the extrude page lay over the print page).

## v1.6.0 (2026-11-17)

- **Manual:** messages on the phone when a print starts, ends, fails,
  is cancelled or pauses (Moonraker's notifier, for example with ntfy),
  switched on with a few lines in `moonraker.conf`.
- **Klipper v0.13.0-827** (was v0.13.0-816): fixes of Klipper, among
  them a possible memory corruption in the motion queue and analog
  readings that arrive in batches.  The main controller firmware stays
  as it is (no Update Firmware needed).  The update manager offers it
  together with this release.
- **KlipperScreen v0.4.7-217** (was v0.4.7-198): the settings are sorted
  into categories, a new WLAN page, the time left takes excluded objects
  into account, and fixes.  The add-on follows: the WLAN symbol reads
  NetworkManager itself (the new WLAN page could not start next to it),
  the touch friendly choice lists work with the new lists, and the
  display options stay on the Light page without an empty "Display"
  category.
- **Cancelled print:** the motors are switched off at the end, as after a
  finished print.  They stayed on until the idle timeout (30 minutes),
  and the warm drivers kept the main board fan at full speed.

## v1.5.0 (2026-11-17)

- **Webcam on phones:** the webcam panel is now also shown on the
  Mainsail dashboard of phones, where Mainsail hides it by default.  This
  applies when Mainsail is set up for the first time; on a printer that is
  already set up, switch it on under **Settings → Dashboard → Mobile**.
- **Nozzle colors in Mainsail:** Extruder (left nozzle) is orange and
  Extruder1 (right nozzle) yellow, as on the touch screen; Mainsail
  cannot rename them.  Set once after the update; a color chosen later
  in Mainsail stays.
- **Manual:** on Android, the browser needs the permission **Nearby
  devices** to open Mainsail (`ERR_TOO_MANY_RETRIES` without it).
- **Manual:** how to reach Mainsail from outside the home network with a
  Cloudflare Tunnel behind a Cloudflare Access login, set up by hand;
  KlipperSnapmakerJ1 itself is not changed.
- **Power loss recovery writes less:** in vase mode or with Z hop the Z
  height changes on almost every move, and the recovery state was
  written to the display's flash memory up to four times a second.  It
  is now written at most every 2 seconds on a Z change (and still at
  once when the power fails).
- **Return to the stock firmware:** when the restore fails after the main
  controller update has started, the display now says that the main
  controller may no longer run Klipper and how to go on, instead of
  only "Nothing was changed".  The boot menu of the display is replaced
  in one step, so it can no longer be left half written.
- **Z offset saved during a print:** it is stored when the print ends;
  this could happen in the middle of the end of print commands.  It now
  waits until they are done.
- **Prints one after the other (job queue):** the cleanup at the end of
  a print (heaters off, carriages parked) could run at the start of the
  next print.  It is now skipped once the next print has started.
- **Main controller update:** when the serial port is lost while the
  image is written (for example a USB adapter), `snapmaker_j1_flash.py`
  now says to run it again, instead of ending with a Python error.
- **Print mode:** the touch screen and the web dialog start a print in
  another IDEX mode by the same rule; the touch screen no longer
  prepares a moved copy while a print is running.  Tests of the print
  file checks and of the main controller image checks run on every
  change (`python -m unittest discover tests`).
- **Backup mode after a filament runout:** the other toolhead went on
  printing 2 mm above the print until the next layer.  It now continues
  where the first one stopped, at the height of the layer.  A tool
  change also brings the bed back to the print height itself, instead
  of leaving that to the next Z move of the file.
- **End of the XY calibration:** the right carriage parked at its endstop
  from before the calibration.  When the new one is smaller, this could
  stop the end with "Move out of range" before the heaters were
  switched off.  It now parks at the newly stored endstop.
- **Manual Z offset calibration (calibration card):** it set the Z
  origin on the bare bed and left out the thickness of the build plate,
  so with the plate back on the first layer started about 5 mm too low,
  in the plate.  It now adds the plate thickness, as the assisted
  calibration does.  **If you used the manual Z offset calibration, run
  a Z offset calibration again before the next print.**
- **Manual heated bed leveling (calibration card):** it now stores the
  rear reference height as the Z origin, as the assisted leveling does
  and as the manual describes; before, the origin stayed as it was.
- **Main controller firmware:** every change now builds the firmware
  from the patch and checks that the patch matches the commits of
  [Nimrasol/klipper](https://github.com/Nimrasol/klipper/tree/j1)
  (branch `j1`).  The firmware itself is unchanged.

- **Z offset at the start of a calibration:** a Z offset that was not
  saved (Z+/Z- during a print) stayed active after a calibration, so the
  next print started that much too high or too low.  A calibration now
  sets it back to 0 when it starts.  A test checks where Z 0 lies after
  a calibration (`tests/test_z_origin.py`).
- **Settings of the touch screen:** they are written in one step and
  stored at once, so switching the printer off right after a change no
  longer loses them.
- **Main controller update:** a damaged request of the bootloader no
  longer ends `snapmaker_j1_flash.py` with a Python error.
- **Duplication and mirror with a file for the right toolhead:** the
  file heats with `M104 T1`, which heated only the right nozzle; the left
  one, which leads in these modes, stayed cold and the print stopped
  ("Extrude below minimum temp").  In these modes every tool now heats
  both nozzles, and every part fan command sets both fans.
- **Update notice:** it no longer offers an update while a heater is on
  (the update restarts Klipper, which stops the main controller then).
- **Return to the stock firmware:** a failure after the maintenance
  system was requested no longer says "Nothing was changed".  A
  non-update `.bin` file on the stick no longer stops the search for the
  update package.  A test checks how often the power loss recovery
  writes its state (`tests/test_power_loss.py`).
- **WLAN symbol:** when the network started after the touch screen, the
  symbol stayed hidden until the next restart; it now appears as soon as
  the network is there.
- **Main controller firmware from the touch screen:** when Klipper stops
  with "Protocol error" (after a Klipper update) or cannot connect to the
  main controller, the error page offers **Update Firmware**: it builds
  the firmware for the installed Klipper and installs it, then Klipper
  starts again.  Before, this needed SSH.
- **Right nozzle Y offset:** a second print on the right nozzle in a row
  printed without its calibrated Y offset (the end of the first print
  had set it back and `T1` changed nothing).  Every tool command now
  sets the offset of its nozzle.
- **Print mode, Cura raft:** the raft (Cura's layers below 0) stayed in
  place while the model moved for another mode; the raft now moves with
  it.  A file printed in mirror mode that was made for duplication (or
  the other way round) is now centered for its mode.  Files with arcs
  (G2/G3, "arc fitting") cannot be moved to another mode: their width is
  not known.
- **PID calibration during a print:** with a cold heater it was accepted
  and moved the carriages; it is now refused during a print.
- **Calibration:** a measurement that fails ends the calibration
  session, so the extra Z travel below the bed is not allowed afterwards.
  Leaving the live height measurement with Home stops the touching until
  the page is shown again.  After a stop during a calibration print the
  touch screen comes back to the main menu; pausing a calibration print
  no longer opens the extrude page.
- **Power loss recovery:** the state is no longer stored in the middle of
  a macro (a tool change could resume with the wrong nozzle), nor after
  the power loss shutdown.  A failing recovery switches the heaters off.
- **Pressure advance (`M900`):** without T it sets the active extruder
  (both in duplication and mirror mode), as Marlin.
- **Park Nozzles, service moves:** after parking, the active carriage
  matches the active extruder again; with a positive Z offset the service
  moves no longer stop with "Move out of range".
- **Update and stock firmware dialogs** check again when confirmed that
  no print runs; a large other `.bin` file on the stick is no longer
  read into memory.  The stock firmware page finds a stick that was
  swapped since the last search.
- **XY calibration:** when a touch fails, the nozzle first leaves the
  calibration hole before the carriage parks; a failed calibration
  measurement switches the heaters off.
- **Reprint of a moved print:** the copy made for another print mode
  carries its mode, so printing it again (history) prints it in that
  mode instead of shifted in the original one; printed in yet another
  mode it always gets a new copy, so its old shift does not stay.
- **Calibration:** a calibration that waits for its next step after the
  test print keeps its place when the print ends on another page; a
  calibration command sent outside a calibration (eg from the console
  during a print) no longer switches the heaters off.
- **Main controller firmware** built on the printer reports the Klipper
  version instead of "?".  The flash tool ignores a too short frame
  instead of stopping, and reports a missing image file plainly.
- **Print mode dialog (web):** a broken file link in the print files no
  longer stops Klipper.
- **Power loss recovery** restores the noise mode, pressure advance,
  speed limit, acceleration and corner speed of the print.  The resumed
  print also continues at the speed of the file: it ran at the maximum
  speed until the file set a new one (the stored speed was converted
  twice).
- **Touch screen:** the calibration print state no longer stays after a
  calibration print ended while another page was shown (later prints
  showed no print page); quitting while a step's commands run no longer
  skips the first step of the next calibration; Continue Printing after a
  runout in a calibration print returns to the calibration page; the
  update notice says why it cannot update while printing or heating and
  asks again later; the WLAN symbol appears when the WLAN device comes up
  after NetworkManager.  In the calibration test print, Pause is off
  before the print starts and after it ended; the filament step names
  its Next button.

## v1.4.0 (2026-11-13)

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
