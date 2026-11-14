# Snapmaker J1 with Klipper: User Manual

This manual shows what the Snapmaker J1 looks like and how it is operated
once it runs Klipper with KlipperSnapmakerJ1.  All screenshots are taken
from the touch screen of a J1 (1280 x 720).

The J1 keeps its own touch screen.  The display module runs Klipper,
Moonraker and KlipperScreen, with a theme in the colors of the stock
display.  The calibration menu with its pictures and animations follows
the stock J1 workflows.  A [web interface](#web-interface) (Mainsail) is available in the
network as well.

For the technical details (hardware, how each stock function is
implemented, configuration) see [Snapmaker_J1.md](Snapmaker_J1.md).

## Contents

- [First start: connect the WLAN and calibrate](#first-start-connect-the-wlan-and-calibrate)
- [The screen at a glance](#the-screen-at-a-glance)
- [Service](#service)
- [Printing](#printing)
- [Temperature](#temperature)
- [Move](#move)
- [Extrude and filament](#extrude-and-filament)
- [Calibration](#calibration)
  - [Heated Bed Leveling](#heated-bed-leveling)
  - [Z Offset Calibration](#z-offset-calibration)
  - [XY Offset Calibration](#xy-offset-calibration)
  - [Offset Calibration Check](#offset-calibration-check)
  - [Vibration Compensation](#vibration-compensation)
  - [PID Auto Tune](#pid-auto-tune)
  - [Build Plate](#build-plate)
- [More](#more)
- [Safety and error messages](#safety-and-error-messages)
- [Web interface](#web-interface)
  - [Webcam](#webcam)
  - [Access from outside the home network](#access-from-outside-the-home-network)
- [Slicer](#slicer)
- [What is implemented](#what-is-implemented)

## First start: connect the WLAN and calibrate

> **Important.**  Do both steps on the first start, before the first
> print.

1. **Connect the WLAN** under **More → Network → WLAN**: choose the
   network and enter its password.  The printer needs the network for
   - the **clock**: the display module has no battery for its clock and
     takes the time from the network (see [Clock](#clock));
   - the **updates** of KlipperSnapmakerJ1, Klipper, Moonraker and
     KlipperScreen; the printer checks for updates as soon as the WLAN is
     connected;
   - the [web interface](#web-interface) and sending files from the
     slicer.
2. **Calibrate** in the [Calibration](#calibration) menu, in this order:
   Heated Bed Leveling, Z Offset Calibration, XY Offset Calibration and
   Offset Calibration Check.  Until then the printer works with the
   values of an uncalibrated J1: the height of the nozzles above the bed
   and the offset between the two nozzles are not right, so the first
   layer fails and a nozzle may touch the bed.  Run Vibration
   Compensation once as well.

## The screen at a glance

![Main menu](manual/main-menu.png)

**Title bar.** The current temperatures of the left nozzle (0), the right
nozzle (1) and the heated bed, the title of the page, the WLAN symbol and
the clock.  The WLAN symbol shows the signal strength: the more bars are
orange, the better the signal; without a connection the symbol is grey.
Tap it to see the network, the signal, the IP address and the address
of the [web interface](#web-interface); **WLAN** there opens the WLAN
page.

<img src="manual/wlan-info.png" width="420">

**Action bar (left).**
- **Back:** returns to the previous page.
- **Circle:** returns to the main menu.
- **Bell:** opens the notifications, for example messages from Klipper.
- **Wrench** (main menu only): opens the [Service](#service) page.

During a print the action bar also shows the emergency stop.  There is no
shutdown button: the J1 is switched off with its power switch.

**Main menu.**
- **Left:** the heaters with their current temperatures and a graph of
  the last minutes.  Tap a heater to set its temperature.
- **Right:** the six main entries, in the order of a print: the print
  itself first, then preparing it, the setup and More last.

| Entry | Content |
| --- | --- |
| Print | files on the printer |
| Temperature | heat, cool down, material presets |
| Extrude | load, unload, extrude, filament sensors, pressure advance |
| Move | home and move the axes, switch the active toolhead |
| Calibration | the J1 calibration menu |
| More | settings, fans, light, network, updates, console, system |

The left nozzle is called **Left Nozzle** (T0, `extruder`) and the right
one **Right Nozzle** (T1, `extruder1`).

## Service

![Service page](manual/service.png)

The wrench button in the action bar of the main menu opens a page for
service work: changing filament, cleaning the nozzles, lubricating the
axes.  It heats without blocking the printer, so other commands still
work while the nozzles heat up.

**Heaters** (one row each):
- **Tile** with the name and the current temperature; a tap sets the
  target, as the target button does.
- **Target:** tap to enter it.  The page keeps it, also after a restart:
  220°C for the nozzles and 60°C for the bed by default.
- **ON / OFF:** switches the heater to its target or off.  A heater that
  is on has an orange frame; a new target applies at once.
- **Load / Unload** (nozzles): available once the nozzle is on and
  within 3°C of its target.  Load feeds 60 mm at 240 mm/min, Unload
  pushes 5 mm and pulls 80 mm back.  The nozzle stays hot for another
  run.  **Load Both / Unload Both** (beside the bed) move both
  extruders at once; two single buttons pressed one after the other run
  one after the other, as Klipper moves one thing at a time.  Loading
  and unloading move both nozzles to the nozzle service position first,
  so the filament falls on the build plate.

**Bottom row:**
- **Nozzle Service:** moves both nozzles 75 mm in from their parking
  positions, clear of the parts there and about 200 mm apart, with the
  bed at least 100 mm below them (homing first if needed).  The button
  then reads **Park Nozzles** and parks them again.  It does not switch
  any heater.
- **Home All:** homes all axes.
- **Distribute Grease:** after lubricating the rails and lead screws,
  moves both nozzles, the bed and the Z axis once over their travel
  (about a minute; down to 10 mm above the build plate).  The build
  plate has to be empty.  Tap again for another run.
- **Fine Tuning:** opens [Fine Tuning](#limits-and-fine-tuning).
- **All Off:** switches all heaters off.

## Printing

### Choosing a file

![Print files](manual/print-files.png)

**Print** lists the files on the printer with the thumbnails of the
slicer.  You can sort them by name, date or size.  The folder
`snapmaker_j1` holds the test prints of the calibration menu.

![File details](manual/print-file.png)

Tapping a file shows its details: layer height, filament, nozzle
diameter, slicer, estimated time and the duration of the last print.
The buttons at the top choose the [print mode](#print-modes).  **Print**
starts the file, **Delete** removes it.

### Nozzle diameter check

![Inconsistent nozzle diameter](manual/nozzle-check.png)

As on the stock display, the printer compares the nozzle diameters the
file was sliced for with the nozzles installed in the printer.  When they
differ, it asks before printing:

- **Cancel:** the print is not started.
- **Continue Anyway:** the print starts with the installed nozzles.

The nozzles are detected by the identification resistor in the hotend.
The same dialog also appears in Mainsail and Fluidd.

### Retraction warning

![Inappropriate retraction distance](manual/retraction-check.png)

As on the stock display, a file that retracts more than 2 mm asks first,
because that can clog the nozzle.  The dialog follows the nozzle diameter
check, for every print start (touch screen, web interface, slicer):

- **Cancel:** the print is not started.
- **Continue Anyway:** the print starts.

The value comes from the slicer settings in the file; in OrcaSlicer, the
retraction of the filament profile counts if it sets one, otherwise that
of the printer profile.

### Print modes

The J1 slicer profiles write the IDEX mode into the file (header or
`M605`).  The print dialog shows the four modes with the one of the file
selected; tap another to print the file in that mode:

| Mode | Behavior |
| --- | --- |
| IDEX | both toolheads print independently (one or two materials) |
| Duplication | both toolheads print the same part side by side |
| Mirror | the right toolhead prints a mirrored copy |
| Backup | after a filament runout the print continues on the other toolhead |

As on the stock display, the printer moves the print in X for the chosen
mode: duplication puts its center at X 80 and mirror at X 75, a
duplication or mirror file printed in IDEX or backup mode goes to the
middle of the bed (X 150).  A mode that does not fit the file explains
why when you tap it:

- duplication, mirror and backup need a file that prints with one
  toolhead;
- duplication needs a model narrower than 160 mm in X, mirror narrower
  than 150 mm.

The purge line of the start G-code stays where it is and does not count
(the OrcaSlicer profile purges across X 0 to 137); the model moves from
its first layer on.  For that the printer prints a copy of the file from
the folder `snapmaker_j1/print_mode` (only the last one is kept).

Reading a large file takes a few seconds; the mode buttons work once it
is done.  In the web interface, the [print mode](#print-mode-in-the-browser)
is chosen with a macro.

During the print, the print page shows the mode next to the elapsed time,
and the part fans of both toolheads.  The elapsed time leaves out pauses:
it stops while the print is paused, for example after a filament runout.

### Pausing, filament runout and filament change

Both toolheads have a filament motion sensor.  When the filament of a
printing toolhead runs out, or the file asks for a filament change
(`M600`), the print pauses and the filament dialog opens:

<table>
<tr><td><img src="manual/filament-change.png" width="420"></td>
<td><img src="manual/filament-insert.png" width="420"></td></tr>
</table>

1. **Unload** pulls the remaining filament back.
2. Insert the new filament into the guide tube until you feel the
   extruder grip it.
3. **Load** heats the nozzle and feeds 100 mm of filament.
4. When filament comes out of the nozzle, tap **Continue Printing**.  If
   none comes out, tap **Load Filament** again.

On a runout the dialog says "Filament Runout Recovery" and names the
nozzle.  In duplication and mirror mode you choose the nozzle in the
dialog.  In backup mode the print continues on the other toolhead
without a dialog.

While the print is paused, its part fans are off.  After the delay set in
[Pause Standby](#pause-standby), the nozzles cool down and the bed stays
at its standby temperature, so the print keeps sticking to the plate.
Resume and Load heat to the print temperatures again.

### Power loss recovery

![Power loss recovery](manual/power-loss.png)

When the mains fails during a print, the printer stores where the print
was.  When Klipper is ready again, the screen offers to continue:

- **Resume:** the nozzles heat up and the printer homes, Z first, so the
  bed moves away from the print.  The nozzles are then primed beside the
  wipers, and the print continues where it stopped.  The nozzle first
  waits 1 mm above the print and then descends slowly, so it melts through
  the filament that oozed out at the stop instead of tearing the print
  off.
- **Later:** keeps the stored print for now.  The dialog appears again at
  the next start.
- **Discard:** deletes the stored print.

Check that the print is still on the plate before you resume.

## Temperature

![Temperature](manual/temperature.png)

- **Heaters:** tap one or more heaters, then enter a temperature or choose
  a preset.
- **Presets:** each one heats both nozzles and the bed:

  | Preset | Nozzles | Bed |
  | --- | --- | --- |
  | PLA | 195 °C | 60 °C |
  | ABS | 220 °C | 90 °C |
  | PETG | 240 °C | 80 °C |
  | FLEX | 210 °C | 60 °C |

- **Cooldown:** turns all heaters off.

The nozzles can be set up to 300 °C and the bed up to 100 °C, as on the
stock firmware.  The PT100 sensors and the heater limits are those of the
stock firmware.

## Move

![Move](manual/move.png)

- **Home:** homes all axes in the stock order (Z, X, Y).
- **X, Y and Z buttons:** move the active toolhead and the bed by the
  chosen distance.  On the J1 the bed moves in Z.
- **T0 / T1:** switches the active toolhead.  The other carriage parks.
- **Gear:** move speeds.

## Extrude and filament

![Extrude](manual/extrude.png)

- **0 / 1:** chooses the nozzle; the buttons show its temperature.
- **Extrude and Retract:** move the filament by the chosen distance and
  speed.
- **Load and Unload:** use the active nozzle at the print temperature
  (220 °C when it is colder than 170 °C), homing first if needed.
  Loading feeds at 240 mm/min, as the stock refill dialog.  Both
  nozzles at once: [Service](#service) page.
- **Left Filament / Right Filament:** switch the filament sensors on or
  off.  The setting is kept after a restart.

Before loading, unloading, extruding or retracting, the nozzle moves just
beside its parking wiper, so the filament falls down between the wiper
and the bed instead of being pressed into the silicone.

### Pressure Advance

![Pressure advance](manual/pressure-advance.png)

This panel adjusts pressure advance for the active nozzle ("Current:
extruder" for the left nozzle, `extruder1` for the right one).  Changes
take effect at once, also during a print.

The value is not stored: after a restart the value of the configuration
applies again (0.02 for both nozzles).  A slicer can also set it per
filament with `M900 K<value>` (`M900 K<value> T1` for the right nozzle).
For a permanent value, add `pressure_advance:` to `[extruder]` and
`[extruder1]` in `printer.cfg`, above the `#*#` block that Klipper
writes itself.

## Calibration

The calibration menu reproduces the "Calibration" page of the stock J1
display: the same five calibrations with the same steps, pictures and
animations.  It adds two entries: PID Auto Tune and Build Plate.

![Calibration menu](manual/cal-menu-bed.png)

- **Left:** the calibrations.  The two entries below the line are
  optional.
- **Right:** what the selected calibration does.
- **Assist Mode:** switches between the assisted workflow, which measures
  with the nozzle contact sensors, and the manual workflow with the
  calibration card.  It is available for Heated Bed Leveling, Z Offset
  Calibration and XY Offset Calibration.  The choice is kept.
- **Start:** starts the calibration.

**Recommended order** (as on the stock display), for a new printer or
after changing a hotend:

1. Heated Bed Leveling
2. Z Offset Calibration
3. XY Offset Calibration
4. Offset Calibration Check

Run Vibration Compensation once, and again after mechanical changes.

**How the steps work.**
- Each step shows a picture or animation, the instructions and its number
  (for example 2/6).
- **Next** is available once the step is done, for example when the
  heaters are hot, the height is right or the test print has finished.
- **Quit** (or Back) asks "The current data will not be saved.  Are you
  sure to quit?" and discards the results of the calibration.

**Where the results go.** The results are stored when a calibration
completes and apply at once: no restart and no Save Config is needed.
They are kept in `snapmaker_j1_variables.cfg`.  The calibrations measure
on the bare heated bed, so they ask you to remove the PEI glass plate.

While the bed is above 40 °C, the pages that ask you to handle the glass
plate show a warning to wait.

### Heated Bed Leveling

The left nozzle touches the bed at the rear center, which is the
reference point.  You then level the bed with the two leveling wheels at
the front, under the bed.

<table>
<tr><td><img src="manual/cal-menu-bed.png" width="420"><br>Assist mode on</td>
<td><img src="manual/cal-menu-bed-manual.png" width="420"><br>Assist mode off</td></tr>
</table>

#### Assisted workflow

<table>
<tr><td><img src="manual/bed-1-remove-plate.png" width="420"><br>1. Remove the PEI glass plate.</td>
<td><img src="manual/bed-2-heat.png" width="420"><br>2. The nozzles heat to 220 °C and the bed to 60 °C.</td></tr>
<tr><td><img src="manual/bed-3-clean.png" width="420"><br>3. Clean both nozzles with the wire brush.</td>
<td><img src="manual/bed-4-left.png" width="420"><br>4. Turn the left wheel as the arrow shows.</td></tr>
<tr><td><img src="manual/bed-5-right-ok.png" width="420"><br>5. Same for the right wheel. A green tick: the height is right.</td>
<td><img src="manual/bed-6-restore.png" width="420"><br>6. Put the glass plate back on.</td></tr>
</table>

**The height indicator** (steps 4 and 5) measures again and again while
you turn the wheel:

- **The orange bar** shows how far the bed is from the reference height.
  It moves towards the middle line as you turn the right way.
- **Within about ±0.5 mm**, the bar is visible.  Further out, one orange
  chevron (or two from 1.5 mm) points to the side where it is.
- **The symbol above the bar** tells which way to turn the wheel:
  clockwise or anticlockwise.
- **A green tick** means the height is within ±0.04 mm.  Next becomes
  available.
- **The value below the bar** is the difference in millimetres.

![Calibrated successfully](manual/cal-success.png)

Every calibration ends with this page.  **Complete** returns to the
calibration menu.

#### Manual workflow (calibration card)

<table>
<tr><td><img src="manual/bedm-1-prepare.png" width="420"><br>1. Remove the glass plate, turn both front wheels clockwise until they stop, clean the nozzle tips.</td>
<td><img src="manual/bedm-2-card.png" width="420"><br>2. Place the calibration card under the left nozzle at the rear point.</td></tr>
<tr><td><img src="manual/bedm-3-jog.png" width="420"><br>3. Lower the nozzle until the card has slight resistance.</td>
<td><img src="manual/bedm-4-left.png" width="420"><br>4. At the front left point, turn the left wheel until the card has the same resistance.</td></tr>
<tr><td><img src="manual/bedm-5-right.png" width="420"><br>5. Same at the front right point with the right wheel.</td>
<td></td></tr>
</table>

The jog buttons move the bed by -1, -0.1, -0.05, +0.05, +0.1 and +1 mm,
and Z shows the current height.  The manual workflow stores the rear
reference height (the Z origin).

### Z Offset Calibration

Sets the right nozzle to the same height as the left one.  The right
toolhead has a thumbwheel that moves its nozzle up and down.

<table>
<tr><td><img src="manual/cal-menu-z.png" width="420"><br>Assist mode on</td>
<td><img src="manual/zm-1-prepare.png" width="420"><br>Assist mode off: first page</td></tr>
</table>

#### Assisted workflow

<table>
<tr><td><img src="manual/z-1-remove-plate.png" width="420"><br>1. Remove the PEI glass plate.</td>
<td><img src="manual/z-2-loosen.png" width="420"><br>2. Loosen the two screws of the right extruder by one turn (H2.0 hex key).</td></tr>
<tr><td><img src="manual/z-3-heat.png" width="420"><br>3. Heat up.</td>
<td><img src="manual/z-4-clean.png" width="420"><br>4. Clean the nozzles.</td></tr>
<tr><td><img src="manual/z-5-wheel.png" width="420"><br>5. Turn the thumbwheel of the right extruder until the bar reaches the middle. Here the bar is out of view and the chevron points left.</td>
<td><img src="manual/z-6-restore.png" width="420"><br>6. Tighten the two screws and put the glass plate back on.</td></tr>
</table>

The left nozzle first measures the reference height.  The right nozzle
then measures continuously while you turn its thumbwheel.  The
adjustment is mechanical, so nothing needs to be stored.

#### Manual workflow (calibration card)

<table>
<tr><td><img src="manual/zm-1-prepare.png" width="420"><br>1. Remove the glass plate and clean both nozzle tips.</td>
<td><img src="manual/zm-2-card.png" width="420"><br>2. Place the calibration card under the left nozzle.</td></tr>
<tr><td><img src="manual/zm-3-jog.png" width="420"><br>3. Lower until the card has slight resistance. This sets the Z origin.</td>
<td><img src="manual/zm-4-right.png" width="420"><br>4. The right nozzle moves to the same point: turn its thumbwheel until the card has the same resistance.</td></tr>
</table>

### XY Offset Calibration

Measures how far the right nozzle is offset from the left one in X and Y,
so that both print at the same place.

<table>
<tr><td><img src="manual/cal-menu-xy.png" width="420"><br>Assist mode on: automatic measurement</td>
<td><img src="manual/cal-menu-xy-manual.png" width="420"><br>Assist mode off: test print with scales</td></tr>
</table>

#### Assisted workflow

<table>
<tr><td><img src="manual/xy-1-remove-plate.png" width="420"><br>1. Remove the PEI glass plate.</td>
<td><img src="manual/xy-2-heat.png" width="420"><br>2. Heat up.</td></tr>
<tr><td><img src="manual/xy-3-clean.png" width="420"><br>3. Clean the nozzles.</td>
<td><img src="manual/xy-4-measure.png" width="420"><br>4. Both nozzles touch the calibration feature in the bed center from all sides. The offsets are measured and stored automatically.</td></tr>
<tr><td><img src="manual/xy-5-restore.png" width="420"><br>5. Put the glass plate back on.</td>
<td></td></tr>
</table>

#### Manual workflow (test print)

The printer prints a model with an X and a Y vernier scale.  The left
nozzle prints the frame and the right nozzle prints the combs.  You read
on the scales how far the right nozzle is off and enter the values.

<table>
<tr><td><img src="manual/xym-1-prepare.png" width="420"><br>1. Install the glass plate and confirm.</td>
<td><img src="manual/xym-2-load.png" width="420"><br>2. Load two PLA filaments of clearly different colors (Go to Load), or tap Next if they are loaded.</td></tr>
<tr><td><img src="manual/xym-3-print.png" width="420"><br>3. The test print runs; Pause and Quit are available. Next becomes available when it has finished.</td>
<td><img src="manual/xym-4-read.png" width="420"><br>4. Read the scales: each line is 0.1 mm.</td></tr>
<tr><td><img src="manual/xym-5-enter.png" width="420"><br>5. Enter the X and Y values (here the second example, X -0.3, Y -0.2). Next applies them.</td>
<td></td></tr>
</table>

**Reading the scales.** Count from line 0 at the X or Y label.  On each
scale, find the line where frame and comb meet exactly:

- in the **+** row the value is positive;
- in the **-** row it is negative.

The two example pictures show X 0.0 / Y 0.0 and X -0.3 / Y -0.2.  If a
value was not 0, run the calibration again until both scales show 0 / 0.

The test print is `gcodes/snapmaker_xy_offset_test.gcode` of this
repository, sliced for the J1 in OrcaSlicer.

### Offset Calibration Check

Prints a small built-in model with both nozzles, to check the Z and XY
offset calibrations.

![Offset calibration check](manual/cal-menu-check.png)

<table>
<tr><td><img src="manual/check-1-plate.png" width="420"><br>1. Make sure the glass plate is installed.</td>
<td><img src="manual/check-2-load.png" width="420"><br>2. Load two PLA filaments of different colors.</td></tr>
<tr><td><img src="manual/check-3-print.png" width="420"><br>3. The check model is printed.</td>
<td><img src="manual/check-4-z.png" width="420"><br>4. Z check: the differently colored surfaces must be flush with each other.</td></tr>
<tr><td><img src="manual/check-5-xy.png" width="420"><br>5. XY check: take the model off and try to break off the four outer squares. If all four can be broken off (not necessarily completely), the XY offset is good.</td>
<td></td></tr>
</table>

If a check fails, repeat the corresponding calibration.

### Vibration Compensation

Finds the input shaper frequency of the X and Y axes with a test print.
The J1 has no accelerometer.

![Vibration compensation](manual/cal-menu-vibration.png)

<table>
<tr><td><img src="manual/vib-1-plate.png" width="420"><br>1. Make sure the glass plate is installed.</td>
<td><img src="manual/vib-2-load.png" width="420"><br>2. Load filament.</td></tr>
<tr><td><img src="manual/vib-3-print.png" width="420"><br>3. The test model is printed. It has four areas, each printed with another compensation frequency (80, 65, 50 and 35 Hz).</td>
<td><img src="manual/vib-4-areas.png" width="420"><br>4. On the X and the Y side of the model, find the area with the least visible vertical ripples.</td></tr>
<tr><td><img src="manual/vib-5-y.png" width="420"><br>5. Choose the best area of the Y side.</td>
<td><img src="manual/vib-6-x.png" width="420"><br>6. Choose the best area of the X side.</td></tr>
</table>

If two areas look equally good and better than the others, choose either.
The chosen frequencies apply at once and are kept.

### PID Auto Tune

Tunes the temperature control of one heater.  The nozzles are tuned at
235 °C, as on the stock firmware, and the bed at 60 °C.

![PID auto tune](manual/cal-menu-pid.png)

- **The page** lists the PID values (Kp / Ki / Kd) of all three heaters,
  each marked "default" or "tuned".
- **The selector** at the bottom chooses Left Nozzle, Right Nozzle or
  Heated Bed.
- **Restore Default** returns the selected heater to the values of the
  configuration.

<table>
<tr><td><img src="manual/pid-1-info.png" width="420"><br>1. Information: keep the printer closed and the part fans off, and do not touch the heater. The nozzles first move off their parking wipers.</td>
<td><img src="manual/pid-2-result.png" width="420"><br>2. While it runs, the page shows the temperature and the progress. At the end it shows the new values.</td></tr>
</table>

An auto tune takes about 5 to 15 minutes.  **Quit** aborts it and keeps
the old values.  The new values apply at once and are stored; Save Config
is not needed.

### Build Plate

![Build plate](manual/cal-menu-plate.png)

The thickness of the build plate on the heated bed: 5.0 mm for the PEI
glass plate of the J1.  The calibrations measure the bare bed, and the
nozzles start printing this much higher.  If you use another build plate,
set its thickness in 0.1 mm steps and tap **Save**.  It applies at once.

## More

![More](manual/more.png)

The entries are arranged in three rows:

| Row | Entries |
| --- | --- |
| Printing | Fine Tuning, Limits, Fan, Pause Standby |
| Settings of the printer | Light, Clock, Network, KlipperScreen |
| Tools and maintenance | Macros, Console, Update, System |

The generic bed level, bed mesh, Z calibrate, input shaper and Save
Config entries are hidden.  The calibration menu covers them, and its
results are stored without Save Config.

### Light

<table>
<tr><td><img src="manual/light.png" width="420"></td>
<td><img src="manual/light-display.png" width="420"></td></tr>
</table>

- **Case Light Brightness:** Off, Low, Medium or Max.  The step is kept
  after a restart.
- **Dim after / Dim to:** like the stock firmware, the case light dims
  after a time without touching the screen, and returns to its step at
  the next touch.
- **Display:** the screen power settings.  The screen switches off after
  15 minutes without touch, both while idle and while printing, as on the
  stock firmware.  A touch switches it on again.

The Light entry is also in the menu of the print page.

### Fan

<table>
<tr><td><img src="manual/fans.png" width="420"></td>
<td><img src="manual/fans-board.png" width="420"></td></tr>
</table>

- **Part fans:** the part fans of both toolheads can be set by hand.
- **Hotend fans:** follow the hotend temperatures.
- **Board fan:** follows the temperature of the main board, which is
  shown next to it.

### Limits and Fine Tuning

<table>
<tr><td><img src="manual/limits.png" width="420"></td>
<td><img src="manual/fine-tuning.png" width="420"></td></tr>
</table>

- **Limits:** changes the acceleration, velocity, cruise ratio and square
  corner velocity until the next restart.
- **Fine Tuning:** used during a print.  It changes the Z offset (baby
  stepping), the speed and the extrusion factor.  **Z-** moves the bed up
  (closer to the nozzle), **Z+** down; both work only on a homed printer.
  Tapping the offset sets it back to 0.
  - **Saving the Z offset:** the button with the check mark next to the
    offset (or **Save** next to the Z offset in the toolhead panel of
    Mainsail) keeps the offset for the next prints.  The printer stores
    it in the Z origin as the calibration does, at once or, during a
    print, when the print ends; the offset shows 0 afterwards and the
    nozzle stays where it is.  No Save Config and no restart are needed.
    After a print with a Z offset, the print page offers the same as
    **Save Z offset**.
  - **Saved:** the button shows the sum of the Z offsets saved since the
    last Z Offset Calibration, which sets it back to 0.

### Pause Standby

![Pause standby](manual/pause-standby.png)

What happens to a paused print:

- **At once:** its part fans turn off.
- **After the delay:** the nozzles cool down and the bed stays at the
  standby temperature.
- **When you resume or load filament:** the nozzles and the bed heat to
  the print temperatures again.

Set the bed standby temperature and the delay here; they are kept.

### Network

<table>
<tr><td><img src="manual/network.png" width="420"></td>
<td><img src="manual/network-name.png" width="420"></td></tr>
</table>

- **WLAN:** choose the network and enter its password; the page also
  shows the address of the printer.  The WLAN symbol in the title bar
  opens it as well.
- **Network Name:** the name of the printer in the network.  The web
  interface is reached at `http://<name>.local`.  Give each printer its
  own name when you have several.

### Clock

![Clock](manual/clock.png)

Sets the time zone and switches the clock in the title bar on or off.
**The clock only runs correctly with the WLAN connected:** the display
module has no battery for its clock and takes the time from the network.
Without a network the printer starts with the last time it knew, so the
clock, the print history and the log files show a wrong time.

### Other entries

| Entry | Content |
| --- | --- |
| KlipperScreen | settings of the screen (language, theme) |
| Macros | runs Klipper macros |
| Console | Klipper's g-code console |
| Update | updates of KlipperSnapmakerJ1, Klipper, Moonraker and KlipperScreen |
| System | system information of the display module; at its end the way back to the [stock firmware](#back-to-the-stock-firmware) |

**Updates.** Update KlipperSnapmakerJ1 first.  Klipper, Moonraker and
KlipperScreen are offered only up to the versions this release is tested
with.  When a new release of KlipperSnapmakerJ1 is out, the touch screen
asks once (not while printing): **Update** starts it, **Later** leaves it
in the Update menu.  **Release candidates** at the end of the Update menu
also offers test versions before a release (`vX.Y.Z-rc.N`), for users who
help testing; switched off, only releases are offered and a test version
already installed stays until the next release.

### Back to the stock firmware

<table>
<tr><td><img src="manual/system-stock.png" width="420"></td>
<td><img src="manual/stock-firmware.png" width="420"></td></tr>
</table>

A fallback, so it sits at the end of **More → System** (scroll down):
**Stock Firmware** returns the printer to the Snapmaker firmware.  It
needs a USB stick with the contents of the stock firmware package (the
official `J1_V*.bin` and the folder `stock-restore`).

1. Plug in the stick and open **Stock Firmware**.  The page searches the
   stick and shows the package and the Snapmaker system it found; **Search
   USB Stick** searches again.
2. Tap **Restore Stock Firmware** and confirm.  Not possible while
   printing.
3. Leave the stick plugged in and do not switch the printer off.  The
   main controller gets the Snapmaker firmware, then the printer restarts
   into its maintenance system, which writes the Snapmaker system, and
   starts the Snapmaker system.

Klipper, its settings, the calibrations and the files on the printer are
deleted.  The Snapmaker setup then starts as on a new printer.  The
[installation](../README.md#installation) describes both ways in full.

## Safety and error messages

### Missing hotend

![Nozzle missing](manual/nozzle-missing.png)

The J1 hotends are pushed in without a cable.  When a hotend is taken out
while the printer is idle:

- its heater stays off and new temperatures for it are rejected;
- the temperature shows **N/A**;
- the "Nozzle Missing" dialog opens.

Once the hotend is back, the dialog closes and the heater works again,
without a restart.

If a hotend is missing during a print, or a sensor reads too high with
the hotend present, the printer stops.

### Printer stopped

When Klipper stops because of an error, the screen shows **Printer
stopped** with the reason and two buttons:

- **Restart:** restarts the firmware.  Use it once the cause is fixed.
- **Menu:** opens the menu.

### Heater protection

The protections of the stock firmware are active:

- **Temperature limits:** the nozzles shut down at 320 °C and the bed at
  110 °C.  Below 5 °C a sensor counts as faulty.
- **Heating check:** a heater that does not heat as expected stops the
  printer.
- **Bed relay check:** the relay of the bed heater is monitored.
- **Supply switches:** the heater supplies are switched off on every
  error.

## Web interface

Besides the touch screen, the printer is operated from any browser in the
network with **Mainsail**, which runs on the printer itself.  Open
`http://snapmaker-j1.local`, or the name set in
[Network Name](#network), or the IP address: a tap on the WLAN symbol in
the title bar shows it.  `.local` needs mDNS, which some networks block
(some routers, mesh systems, guest networks); if it does not open, use
the IP address.  Touch screen and web interface work at the same time
and always show the same state.

On Android, the browser needs the permission **Nearby devices** to reach
the printer: without it, even the IP address fails (Chrome shows
`ERR_TOO_MANY_RETRIES`) although the phone is in the same network.  Allow
it under **Settings → Apps → (browser) → Permissions → Nearby devices**.

### Dashboard

![Mainsail dashboard](manual/web-dashboard.png)

The dashboard shows the printer state with the recent files, the panel
**Snapmaker J1** with the [print mode](#print-mode-in-the-browser), the
temperatures of **Extruder** (left nozzle), **Extruder1** (right nozzle)
and **Heater Bed** with their history, the toolhead and the console.

- **Toolhead:** homing (**ALL**) and moving the axes.  X moves the active
  carriage; the other one stays parked.
- **Emergency Stop** (top right) stops the printer at once, as on the
  touch screen.
- **Cooldown** switches all heaters off.

<table>
<tr><td><img src="manual/web-extruder.png" width="420"></td>
<td><img src="manual/web-misc.png" width="420"></td></tr>
</table>

- **Extruder:** **T0** and **T1** select the active toolhead (the other
  carriage parks), extrude and retract the active one, and set its
  [pressure advance](#pressure-advance) and smooth time.  Choose the
  nozzle in the **Extruder** field to set the values of the other one.
- **Machine:** speed and acceleration limits.  The noise mode sets them
  at the start of a print; values changed here apply until then.
- **Miscellaneous:** case light and the two part fans.  The hotend fans
  are only shown: they run on their own while a hotend is hot.  The
  supply switches and the electronics fan of the main board are hidden;
  the firmware switches them.

### Dialogs

![Nozzle diameter dialog in Mainsail](manual/web-prompt.png)

The [nozzle diameter check](#nozzle-diameter-check) and the
[retraction warning](#retraction-warning) at the start of a print and the
[missing hotend](#missing-hotend) message appear in the browser as well as on the touch screen; answering in one place closes the
dialog in the other.  The filament runout and change dialog and the
[power loss recovery](#power-loss-recovery) are shown on the touch
screen only: in the browser, a paused print is continued with
**Resume**.

### Print mode in the browser

<img src="manual/web-panel.png" width="474">

A print started with **Upload & Print** or in **G-Code Files** prints in
the mode of the file.  To choose another mode, tap
**SNAPMAKER PRINT MODE** in the panel **Snapmaker J1**.  While a print is
paused, the panel also offers **SNAPMAKER PAUSE HEAT** (heat the print
again).

<table>
<tr><td><img src="manual/web-print-mode-files.png" width="400"><br>1. Choose the file: the newest first, six per page (<b>Older</b> and <b>Newer</b> turn the pages).</td>
<td><img src="manual/web-print-mode.png" width="400"><br>2. Choose the mode: the mode of the file is highlighted, a mode that does not fit the file is listed with the reason.  The print starts with this tap.</td></tr>
</table>

The checks and the moving of the print are those of the
[touch screen](#print-modes).  In Fluidd, the macro
`SNAPMAKER_PRINT_MODE` opens the same dialogs.

The printer sets the panel up once, as long as the macros of Mainsail are
not set up otherwise: Mainsail then uses its expert macro mode, without
the long **Macros** panel (**Settings → Macros** switches back).  The
list look of these dialogs comes from `.theme/custom.css` in the
configuration, which the printer writes unless it holds a theme of your
own.

### Macros

All J1 commands can be typed in the console, or be added to a panel in
**Settings → Macros**, among them:

| Macro | Function |
| --- | --- |
| `SNAPMAKER_LOAD_FILAMENT`, `SNAPMAKER_UNLOAD_FILAMENT` | heat a toolhead and load or unload filament (`TOOL=0` or `1`, `2` both at once; `SERVICE=1` at the nozzle service position) |
| `SNAPMAKER_NOZZLE_SERVICE`, `SNAPMAKER_NOZZLE_PARK` | move both nozzles in for service, park them again |
| `SNAPMAKER_DISTRIBUTE_GREASE` | move all axes once over their travel after lubricating |
| `SNAPMAKER_PRINT_MODE` | [choose a file and its print mode](#print-mode-in-the-browser) (`FILENAME=` skips the file list) |
| `SNAPMAKER_SET_PRINT_MODE` | IDEX mode: full control, duplication, mirror, backup |
| `SNAPMAKER_NOISE_MODE` | stock noise mode: normal, silent, loud |
| `SNAPMAKER_SET_PAUSE_STANDBY`, `SNAPMAKER_PAUSE_HEAT` | [pause standby](#pause-standby) and heating a paused print again |
| `SNAPMAKER_SET_VIBRATION_FREQ` | vibration compensation frequency |
| `M600` | pause for a filament change |
| `T0`, `T1` | select the toolhead |

The `M...` and `G...` macros are the Snapmaker and Marlin g-codes of the
slicer profiles.  The `SNAPMAKER_CAL_...`, `SNAPMAKER_CALIBRATE_...` and
`SNAPMAKER_BED_LEVEL` macros are the steps of the
[calibration menu](#calibration).  Run the calibrations on the touch
screen: the menu guides through the adjustments on the printer, shows
the pictures and stores the results.

### G-code files and history

![G-code files](manual/web-files.png)

**G-Code Files** lists the files on the printer with their thumbnails
and slicer data.  **Upload & Print** (top right), drag and drop, or the
slicer upload a file; a print started here is checked for the nozzle
diameter as on the touch screen.  The folder `snapmaker_j1` holds the
test prints of the calibration menu.

![Print history](manual/web-history.png)

**History** shows all prints with their time, filament use and result,
and the statistics.

### Console

![Console](manual/web-console.png)

The console sends commands to Klipper and shows its messages, for
example `SNAPMAKER_LOAD_FILAMENT TOOL=1` or `M605 S2`.

### Machine: configuration, updates and logs

![Machine page](manual/web-machine.png)

- **Config Files:** `printer.cfg` holds the settings of this printer and
  can be edited here.  The folder `snapmaker_j1` holds the J1
  configuration of KlipperSnapmakerJ1; it is replaced by every update,
  so changes belong in `printer.cfg`.  The calibrations store their
  results in `snapmaker_j1_variables.cfg`.
- **System Loads:** main controller and display module (processor, memory,
  WLAN).
- **Update Manager:** updates of KlipperSnapmakerJ1 ("Snapmaker J1
  support for Klipper"), Klipper, Moonraker, KlipperScreen and Mainsail.
  Update KlipperSnapmakerJ1 first: Klipper, Moonraker and KlipperScreen
  are offered only up to the versions it is tested with.
- **Log Files:** the Klipper and Moonraker logs for troubleshooting.

Restart Klipper (top right power menu, or after editing the
configuration) only while all heaters are off and no print is running.

Fluidd is not installed.  Its hosted page (app.fluidd.xyz) is served
over https only, and browsers do not let it connect to the printer.

### Webcam

<img src="manual/webcam.jpg" width="480" alt="USB webcam in the USB port of the J1">

A USB webcam in the USB port of the display module shows in Mainsail:
on the dashboard and full size on the page **Webcam**.  It has to be a UVC
camera with MJPEG, as most USB webcams are; cameras without MJPEG are not
streamed (the display module would have to encode every frame).  Action
cameras in webcam mode do not always work, a DJI Action 2 for example
does not.

1. Plug in the camera.  The first time, the touch screen asks
   **Install the webcam support?**: **Install** loads the streamer
   (ustreamer) from the network; this takes several minutes, printing is
   possible meanwhile.  The screen reports **Webcam ready** when it is
   done.
2. Mainsail shows the camera as **J1**: on the dashboard (left below)
   and on the page **Webcam**.  Name, rotation and mirroring are set in Mainsail
   (**Settings → Webcams → Edit**, right) and are kept.

<table>
<tr><td><img src="manual/web-webcam-panel.png" width="420"></td>
<td><img src="manual/web-webcam-settings.png" width="420"></td></tr>
</table>

![Webcam page in Mainsail](manual/web-webcam.png)

The stream starts when the camera is plugged in and stops when it is
unplugged; meanwhile Mainsail does not show the camera.  Mainsail has its
own dashboard layout for phones; there the webcam is shown too.  If it is
missing on a phone, switch it on in Mainsail under **Settings →
Dashboard → Mobile** (eye symbol next to **Webcam**).  It runs at
1280 x 720 with 15 frames per second, which needs about 1% of the
processor of the display module.  The touch screen itself does not show
the camera.

### Access from outside the home network

KlipperSnapmakerJ1 itself makes the printer reachable only in the home
network.  This section shows one way to reach Mainsail from anywhere with
a **Cloudflare Tunnel**, set up by hand; nothing in KlipperSnapmakerJ1 is
changed for it, and its updates do not touch it.

**Mainsail has no login.**  Whoever reaches it controls the printer:
heaters, motors, files.  Never make it reachable from the Internet without
an access check in front of it; here that is **Cloudflare Access**, which
lets only you in after a login (GitHub in this example).

You need a Cloudflare account (the free plan and the free Zero Trust plan
are enough) and a domain whose DNS is managed by Cloudflare.  The tunnel
is an outgoing connection from the printer, so no port is opened on the
router.

1. **Login method:** in the Zero Trust dashboard
   (`one.dash.cloudflare.com`), **Settings → Authentication → Login
   methods → Add new → GitHub** (in newer dashboards **Integrations →
   Identity providers**).  In GitHub, create an OAuth app under
   **Settings → Developer settings → OAuth Apps → New OAuth App** with
   - Homepage URL: `https://<team>.cloudflareaccess.com`
   - Authorization callback URL:
     `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback`

   `<team>` is the team domain of your Zero Trust account.  Enter the
   client ID and a new client secret of the OAuth app in Cloudflare,
   save, and check it with **Test**.
2. **Access check first:** **Access → Applications → Add an application
   → Self-hosted** (newer: **Access controls → Applications**).  Public
   hostname for example `j1.example.com`.  Add a policy with action
   **Allow** and **Include → Emails** with the e-mail address of your
   GitHub account; not **Everyone**, which would let in anybody with a
   GitHub account.  Under login methods allow only **GitHub**.  The
   session duration (for example one week) sets how often you log in
   again.
3. **Tunnel:** **Networks → Tunnels → Create a tunnel → Cloudflared**,
   any name.  Cloudflare shows an install command with a token
   (`cloudflared service install eyJ...`); the token is the same for every
   operating system.  Keep it secret: it gives access to the tunnel.
4. **On the printer**, logged in over SSH (`ssh pi@snapmaker-j1.local`
   or the IP address, password `klipper`; change it with `passwd`, at the
   latest now that the printer is reachable from outside), install
   cloudflared for the processor of the display module (`armhf`) and the
   tunnel as a service, which starts with the printer:

   ```
   curl -fsSL -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf.deb
   sudo dpkg -i /tmp/cloudflared.deb
   sudo cloudflared service install <token>
   ```

   The tunnel shows as **Healthy** in the dashboard.
5. **Route:** in the tunnel, **Public Hostname** (newer: **Published
   application routes**) **→ Add**: subdomain `j1`, your domain, service
   `http://localhost:80` (`http`, not `https`: Cloudflare encrypts the
   connection to the browser).  Do not leave the subdomain empty, or the
   domain itself leads to the printer.

**Check it** in a private browser window or on a phone with mobile data:
`https://j1.example.com` must show the Cloudflare login and nothing of
Mainsail before you log in.  After the login, Mainsail and the webcam work
as at home.

- The tunnel survives updates of KlipperSnapmakerJ1, Klipper, Moonraker,
  KlipperScreen and Mainsail.  Reinstalling the display system or going
  back to the stock firmware removes it; step 4 sets it up again with the
  same token.
- cloudflared does not update itself; installing a newer package as in
  step 4 (without the last line) keeps the tunnel.
- To remove it: `sudo cloudflared service uninstall` and
  `sudo apt remove cloudflared`, then delete the tunnel in the dashboard.

## Slicer

Files sliced with a J1 printer profile (for example in OrcaSlicer) print
without changes: the Snapmaker and Marlin g-codes of the J1 profiles are
implemented as macros.  The IDEX mode of the file is applied when the
print starts, and pressure advance (`M900`) and vibration compensation
(`M593`) set by the slicer are applied too.

To send files from the slicer, add the printer as a Klipper (Moonraker)
host with `snapmaker-j1.local`.

The print area of the J1 is **324 × 200 mm** with its origin at X 0,
Y 0, as in the stock firmware: the center of the bed is at **X 162,
Y 100**, not at X 150.  The J1 profiles of OrcaSlicer have it so
(**Printer settings → Basic information → Printable area**: size 324 ×
200, origin 0 / 0).  A profile with a width of 300 mm places every print
12 mm left of the center.

## What is implemented

| Area | Function |
| --- | --- |
| Printing | IDEX, duplication, mirror and backup mode from the file or chosen on the touch screen or in the browser, with the model moved in X; tool changes with parking; pause and resume with parking, priming and wiping |
| Print start | nozzle diameter check against the installed nozzles, retraction warning above 2 mm |
| Filament | motion sensors on both toolheads, runout and change dialog, load and unload beside the wipers |
| Service | service page: heaters on/off with kept targets, load and unload (both at once), nozzle service position, homing, grease distribution |
| Power loss | recovery of the interrupted print, offered on the screen at the next start |
| Calibration | bed leveling, Z offset, XY offset (assisted and manual), offset check, vibration compensation, PID auto tune, build plate thickness |
| Results | stored at once, no restart or Save Config |
| Heaters | stock limits and protections; a missing hotend only blocks its heater; temperatures without a valid reading show N/A |
| Light and screen | case light in four steps, dimmed after a time without touch; the screen switches off after 15 minutes |
| Network | WLAN symbol with signal strength and the address of the web interface; network name `<name>.local` |
| Webcam | a USB webcam (UVC with MJPEG) streams to Mainsail while it is plugged in |
| Noise | the stock noise modes (normal, silent, loud), set by the slicer (`M2000 S113`) or `SNAPMAKER_NOISE_MODE`; every print starts in normal mode |
| Firmware | Klipper on the main controller, installed through the factory bootloader; the stock firmware can be installed again the same way |

Not ported: the stock display application, which cannot control Klipper,
and the CNC and laser functions of the shared display code.
