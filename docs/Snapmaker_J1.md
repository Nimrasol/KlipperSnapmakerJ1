# Snapmaker J1

This document describes the Klipper support for the Snapmaker J1 IDEX
printer: the hardware as recovered from the stock software, how every
printer specific function of the stock software maps to Klipper, and
how to build, install and calibrate the printer.

The port follows one rule: use stock Klipper wherever it provides the
needed behavior, and add code only where it does not.  The additions
are a GD32F305 chip option, support for the J1 factory bootloader, four
small host modules and a set of g-code macros.

## Sources

The analysis is based on these artifacts:

| Artifact | Identity | Use |
| --- | --- | --- |
| Main controller flash dump (first 512KiB of 1MiB, via SWD) | application at 0x08002800, byte identical to the stock V2.2.14 update image | firmware version and memory layout |
| Main controller bootloader dump (0x08000000-0x080027FF) | "V1.0.3-boot" | boot and update protocol (disassembled) |
| [SnapmakerController-IDEX](https://github.com/Snapmaker/SnapmakerController-IDEX) | V2.2.14 plus one fix, matches the installed firmware | behavioral reference for the main controller |
| Display eMMC dump (Quectel SC20-W, Android) | userdata: `com.snapmaker.j1` (Feb 2026), `mc.bin` V2.2.14 | display workflows, update packages, calibration prints |

The display application in `/system/app/j1` is an outdated 2022 base
version; the active application is the one installed in
`/data/app/com.snapmaker.j1-2/base.apk`.

## Hardware

### Main controller

* MCU: GigaDevice GD32F305VG (Cortex-M4, 1MiB flash, 96KiB RAM).  The
  stock firmware reports "GD32F105RCT6", which is only a leftover
  machine name.
* Clock: 25MHz crystal, 120MHz system clock (HSE/5 -> PLL2 x10 ->
  PREDIV1 /5 -> PLL x12), APB1 60MHz.
* Host link: USART1 remapped to PB6 (TX) / PB7 (RX), connected to the
  display module (Linux `/dev/ttyMSM1`, Android `/dev/ttyHSL1`).  The
  stock firmware uses 115200 baud.

### Flash layout

| Address | Size | Content |
| --- | --- | --- |
| 0x08000000 | 10KiB | factory bootloader (last page also holds the serial number) |
| 0x08002800 | up to 0x080F9800 | application |
| 0x080F9800 | 2KiB | factory data (build plate thickness) |
| 0x080FA000 | 4KiB | crash dump |
| 0x080FB000 | 8KiB | power loss data |
| 0x080FD000 | 4KiB | update header (see below) |
| 0x080FE000 | 8KiB | Marlin settings |

Pages are 2KiB below 512KiB and 4KiB above (second flash bank).

### Factory bootloader

The bootloader validates a 101 byte header at 0x080FD000 (the start of
a stock `mc.bin`):

| Offset | Field |
| --- | --- |
| 0 | `"snapmaker update.bin"` |
| 22 | image type (must be 3) |
| 81 | status (0xAA02 update requested, 0xAA03 updating, 0xAA04 update done, 0xAA05 application normal) |
| 83 | application length |
| 87 | application checksum |
| 91 | application start (2KiB aligned, at least 0x08002800) |
| 97 | header checksum over bytes 0-96 |

Checksums are the inverted 32 bit sum of the big-endian 16 bit words.
With status 0xAA05 and a matching application checksum the bootloader
starts the application; with 0xAA02 it waits for an image from the
display; any other status also makes it wait.  After an update it
starts the new application once with status 0xAA04 and relies on the
application to restore 0xAA05.  Updates use the SACP protocol (frame
`AA 55 len16 ver dst crc8 src attr seq16 set id data sum16`): the
bootloader accepts a new header (command set 0xAD, id 0x01), requests
2KiB chunks by byte offset (0xAD/0x02, answered with result, offset,
length and data) and reports the result (0xAD/0x03).

### Pins

| Function | Pin | Notes |
| --- | --- | --- |
| X (left carriage) step/dir/enable | PB10 / PE15 / !PB11 | endstop ^PD13 (min) |
| X2 (right carriage) step/dir/enable | PC5 / !PC4 / !PB0 | endstop ^PB2 (max) |
| Y step/dir/enable | PE5 / PE4 / !PE6 | endstop ^PB9 (min) |
| Z step/dir/enable | PE11 / !PE10 / !PE12 | endstop ^PE7 (max, bed down) |
| E0 step/dir/enable | PB13 / PB12 / !PB14 | |
| E1 step/dir/enable | PC2 / !PC1 / !PC3 | |
| TMC2209 UART | TX PD8, RX PD9 | address 3, selected by mux PB15/PD10/PD11 |
| Hotend heaters | PE14, PE13 | |
| Hotend sensors | PA3, PA1 | PT100 with amplifier (stock table 25) |
| Bed heater | !PA10 | solid state relay, feedback PA12 (high = powered) |
| Bed sensor | PC0 | EPCOS 100K, 4.7K pullup |
| Board sensor | PA2 | EPCOS 100K, controls the electronics fan |
| Part fans | PC9 (T0), PC7 (T1) | |
| Hotend fans | PA8 (T0), PC8 (T1) | on above 60C |
| Electronics fan | PC6 | on above 45C board temperature |
| Case light | PB8 | PWM, default 150/255 |
| Nozzle contact switches | ^!PA7 (T0), ^!PE8 (T1) | low when touching |
| Contact switch power | PD14 | |
| Filament motion sensors | PA4 (T0), PA0 (T1) | analog |
| Nozzle identification | PA5 (T0), PA6 (T1) | analog |
| Board revision | PB1 | analog divider |
| Mains failure input | PC12 (rev 1), PD15 (rev 2) | high = failure, pullup |
| Power switches | PC10 motors, PC11 toolhead heaters, PA9 bed, PD4 display | all on at boot |
| StallGuard outputs | rev 1: PE3 shared; rev 2: X PD12, X2 PE3, Y PB5, Z PE9 | |

TMC mux selection (PB15, PD10, PD11): X 010, X2 001, Y 100, Z 110,
E0 111, E1 011 (1 = high).

### Mechanics

* X1 range -13..324 (homes at -13), X2 range 0..337 (homes at 337 or
  at its calibrated offset), minimum carriage distance 24mm.
* Y 0..202, Z 215mm travel (the bed homes down to Z max).
* Steps: X/Y 80/mm, Z 1600/mm, E 138.58/mm (16 microsteps).
* Currents (RMS): X/X2 1.0A, Y 1.4A, Z 1.0A, E 0.8A, sense 0.150 Ohm,
  stealthChop on all axes.
* Bed leveling: three knobs (rear center fixed, front left, front
  right) at (162,187), (47,7), (277,7).
* XY calibration feature in the bed center (162,101), probed from 1.2mm
  below the bed surface with the build plate removed.

## Stock behavior and its Klipper implementation

| Stock function | Klipper implementation | New code |
| --- | --- | --- |
| Motion, IDEX full control, duplication, mirror | `cartesian` + `[dual_carriage]`, `SET_DUAL_CARRIAGE`, `SYNC_EXTRUDER_MOTION`; `M605` macro | macros |
| Backup mode (continue on the other toolhead after a runout) | runout macro switches the tool and remaps T/M104/M106 | macros |
| Print mode from the file header (`;Extruder Mode:`) | `SNAPMAKER_FILE_MODE` from `SDCARD_PRINT_FILE` | `snapmaker_j1` |
| Homing order Z, X, Y and tool restore | `[homing_override]` | macros |
| Tool change with Z hop and parking | `T0`/`T1` macros | macros |
| TMC2209 behind a UART mux | `[tmc2209]` with `select_pins` | none |
| Noise modes (normal/silent/loud) | `SET_VELOCITY_LIMIT`, `SET_TMC_FIELD en_spreadcycle` | macros |
| Input shaping (M593) | `[input_shaper]` per carriage | macros |
| Linear advance (M900) | pressure advance | macros |
| PT100 hotend sensors | `[adc_temperature]` from the stock table | none |
| Thermal protection | `[verify_heater]`, min/max temp | none |
| Heater supply switches cut on errors | `[output_pin]` with `shutdown_value: 0` | none |
| Bed relay self check | continuous feedback monitoring of PA12 | `snapmaker_j1` |
| Board revision detection | ADC check against the configured revision | `snapmaker_j1` |
| Nozzle type detection | ADC classification, `SNAPMAKER_QUERY_HARDWARE` | `snapmaker_j1` |
| Fans (part, hotend, electronics) | `fan_generic`, `heater_fan`, `temperature_fan` | none |
| Case light (M355) | `[output_pin]` | macros |
| Nozzle contact probing (Z) | probe interface using the active nozzle's switch | `snapmaker_j1_probe` |
| Z offset calibration | `PROBE` + `SNAPMAKER_Z_ENDSTOP_ADJUST` | `snapmaker_j1_probe` |
| Heated bed leveling (knobs) | `[screws_tilt_adjust]` | none |
| XY offset calibration of T1 | horizontal probing of the bed center feature | `snapmaker_j1_probe` |
| T1 nozzle height adjustment | `SNAPMAKER_NOZZLE_HEIGHT` | `snapmaker_j1_probe` |
| Build plate thickness | Z origin shift | macros |
| Analog filament runout/jam detection | motion sensor based on the analog reading | `snapmaker_j1_filament_sensor` |
| Pause / resume with parking, priming and wiping | `PAUSE`/`RESUME` macros, `SAVE_DUAL_CARRIAGE_STATE` | macros |
| Power loss detection and recovery | state checkpoints, shutdown, `M23`/`M26`/`M24` resume | `snapmaker_j1_power_loss` |
| Factory bootloader boot state | restore "application normal" at startup | MCU |
| Firmware update via the display | `scripts/snapmaker_j1_package.py` | script |
| Calibration menu and workflows | KlipperScreen add-on | add-on |

Not ported: the SACP display protocol (the stock display application
cannot control Klipper), CNC/laser functions of the shared display code,
StallGuard crash detection during calibration probing (the probe
switches and the build plate check below are used instead) and the
simultaneous T0/T1 parking move of `M2000 S200` (tool changes park the
inactive carriage first).

## Klipper changes

### MCU

* `MACH_GD32F305`: stm32f105 "connectivity line" register set with the
  120MHz clock tree above, Cortex-M4 code generation.
* `STM32_FLASH_START_2800`: 10KiB bootloader offset.
* `STM32_SNAPMAKER_BOOTLOADER` (`src/stm32/snapmaker_boot.c`): at
  startup it rewrites the update header status to 0xAA05 when it is not
  set (as the stock firmware does), and a bootloader request sets
  0xAA02 and resets so the factory bootloader waits for a new image.

### Host modules

#### [snapmaker_j1]

```
[snapmaker_j1]
hardware_version: 2
#   Board revision the configuration is written for (the power loss and
#   StallGuard wiring differs). Klipper shuts down if the board reports
#   another revision. This parameter must be provided.
hw_version_pin: PB1
nozzle_id_pin_t0: PA5
nozzle_id_pin_t1: PA6
#   Analog inputs for the board revision and nozzle identification.
#bed_feedback_pin:
#   Input reporting whether the bed heater is powered. If set, Klipper
#   shuts down when the feedback disagrees with a fully on or fully off
#   heater for bed_feedback_time seconds.
#bed_feedback_time: 2.0
```

Commands: `SNAPMAKER_QUERY_HARDWARE` reports the detected board revision
and nozzle types; `SNAPMAKER_FILE_MODE FILENAME=<file>` selects the IDEX
mode from the file header.  Status: `hardware_version`,
`detected_hardware_version`, `nozzle_t0`, `nozzle_t1` (`material`,
`diameter`, `adc_mv`), `bed_feedback`.

#### [snapmaker_j1_probe]

```
[snapmaker_j1_probe]
pin_t0:
pin_t1:
#   Contact switch pins of the left and right nozzle.
#power_pin:
#   Pin powering the switches while probing or calibrating.
#power_on_delay: 0.100
z_offset:
#speed, lift_speed, samples, sample_retract_dist, samples_result,
#samples_tolerance, samples_tolerance_retries:
#   See the "probe" section.
calibration_points:
#   X, Y of the calibration points, one per line. The first point is
#   the XY calibration feature in the bed center.
#travel_z: 15
#travel_speed: 150
xy_probe_z:
#   Height for horizontal probing (calibrations use -1.2mm minus the
#   build plate thickness).
#xy_probe_distance: 15
#xy_probe_speed: 13.3
#xy_probe_slow_speed: 1.3
#xy_retract_dist: 1
#xy_samples: 5
#xy_tolerance: 0.25
#max_t1_offset: 5
#max_center_offset: 5
```

The module registers as the printer `probe` and uses the switch of the
active carriage (the other carriage is parked first).  Besides the
calibration session commands (see Calibration) it provides
`SNAPMAKER_PROBE_XY_CENTER [TOOL=] [Z=]` and
`SNAPMAKER_Z_ENDSTOP_ADJUST OFFSET=` (moves the Z origin up by OFFSET,
updating `position_endstop` and `position_max` of `[stepper_z]`).  The
descent for XY probing is a probing move: a nozzle contact before
reaching the calibration height aborts with a request to remove the
build plate.  Status: `calibration` (`active`, `datum`,
`height_difference`, `height_valid`, `z_origin_offset`, `t1_offset`,
`bed_center_offset`) in addition to the probe status.

#### [snapmaker_j1_filament_sensor]

```
[snapmaker_j1_filament_sensor my_sensor]
adc_pin:
extruder:
#check_distance: 3
#threshold: 0.00366
#   Minimum change of the normalized reading per check_distance of
#   extrusion (stock: 15 counts of 4096 on revision 2 boards, 8 on
#   revision 1).
#check_count: 3
#dead_space_min: 0.0146
#dead_space_max: 0.991
#dead_space_distance: 4
#pause_on_runout, runout_gcode, insert_gcode, event_delay, pause_delay:
#   See the "filament_switch_sensor" section.
```

#### [snapmaker_j1_power_loss]

```
[snapmaker_j1_power_loss]
sense_pin:
#debounce_delay: 0
filename:
#   File holding the recovery state.
#save_interval: 30
#   Also store the state every save_interval seconds while printing (it
#   is always stored on a layer change and on a mains failure).
#save_objects:
#   Printer objects whose status is stored with the state.
resume_gcode:
#   Template run by SNAPMAKER_POWER_LOSS_RESUME before the print
#   continues; the stored state is available as "state".
```

While printing the module records, every 250ms, the file position and
g-code state together with the time the corresponding moves finish.
On a mains failure it selects the last state whose moves were executed,
shuts Klipper down (all heaters and heater supplies off, motion stops)
and writes the state atomically.  `SNAPMAKER_POWER_LOSS_RESUME` runs
`resume_gcode` (heat, home with Z first - the bed moves away from the
print -, restore the IDEX mode, prime, move back) and continues the
file at the stored position.  `SNAPMAKER_POWER_LOSS_STATUS` and
`SNAPMAKER_POWER_LOSS_CLEAR` report and discard the state.  The state
is discarded when a print completes, is cancelled or a new print starts;
a paused or failed print keeps it.

The stock firmware lowers the bed by 5mm after a mains failure.
Klipper cannot run new moves after an emergency stop, so the nozzle
remains above the print until the recovery homes Z.

## Building and installing

On the Klipper host (the display module), with Klipper, Moonraker and
KlipperScreen installed:

1. Install this repository:
   ```
   cd ~
   git clone https://github.com/Nimrasol/klipper-snapmaker-j1.git
   ./klipper-snapmaker-j1/install.sh --apk base.apk
   ```
   This links the host modules into `~/klipper/klippy/extras`, the
   configuration into `~/printer_data/config/snapmaker_j1` (included
   from `printer.cfg`), the KlipperScreen add-on, theme and menu, and
   adds the Moonraker update manager entry.  Check `hardware_version`
   and the mains failure pin in the printer configuration.
2. Build and package the main controller firmware:
   ```
   ./klipper-snapmaker-j1/firmware/build.sh
   ```
   The script applies `firmware/klipper-gd32f305-snapmaker.patch` (the
   GD32F305 chip option and the factory bootloader support) to a copy
   of the installed Klipper, builds it with
   `firmware/snapmaker-j1.config` (the options listed at the top of
   `printer-snapmaker-j1-2022.cfg`) and packages the result into
   `firmware/out`.
3. Install the firmware, either
   * through the stock display: copy `update.bin` to a USB stick and
     use the display's firmware update from USB, or
   * via SWD: program `klipper.bin` at 0x08002800 and
     `boot-header.bin` at 0x080FD000 (keep the bootloader).

Updates of this repository are offered by the Moonraker update manager
(KlipperScreen "Update", Mainsail, Fluidd).  When an update of Klipper
changes the protocol to the main controller, rebuild and install the
firmware.

The display module also powers the Klipper host when Klipper runs on
it; PD4 is therefore an initial pin of the firmware and never switched
off.  To return to the stock firmware, request the bootloader with
Klipper stopped (see [Bootloader_Entry.md](https://www.klipper3d.org/Bootloader_Entry.html)):
```
echo $'~ \x1c Request Serial Bootloader!! ~' >> /dev/ttyMSM1
```
and install a stock update package with the display's USB firmware
update, or program the stock `mc.bin` via SWD.  (When the stock display
finds the main controller waiting in its bootloader it installs its
cached package - after a Klipper installation that is the Klipper
package.)

## Calibration

The stock calibrations measure on the bare heated bed (build plate
removed) with both nozzles at 220C and the bed at 60C; the print
surface is the measured bed surface plus the build plate thickness.
Results are collected in a calibration session and only stored when the
calibration completes (`SNAPMAKER_CAL_FINISH SAVE=1`, then
`SAVE_CONFIG`); quitting discards them.

### Calibration menu (KlipperScreen)

The touch screen menu reproduces the stock "Calibration" page with its
five entries; the first three can be switched between the assisted
(sensor) and the manual workflow ("Assist Mode"):

| Entry | Assisted workflow | Manual workflow |
| --- | --- | --- |
| Heated Bed Leveling | remove plate, heat, clean nozzles, rear reference, live height bar while turning the front left and front right wheels, restore | checklist, calibration card at the rear point, then the front wheels at the same height |
| Z Offset Calibration | remove plate, loosen the right extruder screws, heat, clean, live height bar while turning the right extruder thumbwheel, tighten and restore | checklist, calibration card with the left nozzle (sets the Z origin), then the right nozzle thumbwheel at the same height |
| XY Offset Calibration | remove plate, heat, clean, automatic probing of the bed center feature, restore | test print of X/Y line patterns, then entering the observed shift |
| Offset Calibration Check | plate check, load filament, check print, Z and XY evaluation pages | - |
| Vibration Compensation | plate check, load filament, test print with 80/65/50/35Hz areas, choice per axis | - |

The live bar follows the stock HorizontalPrecisionIndicator: the orange
bar (0.08 wide) moves by the bar width per millimetre and is visible
within about +/-0.54mm; beyond that one orange chevron, from 1.5mm two,
point to the side where it is.  Above the bar the stock pictures tell
the direction to turn the wheel: clockwise below -0.04mm,
anticlockwise above +0.04mm, a green tick in between, which also
enables Next.  As on the stock display the right nozzle reading is
inverted (the bed leveling shows the measured difference itself); the
main controller firmware reports the trigger height in the same sense
as `height_difference` (Z+ away from the nozzle).
Two stock defects are not reproduced: the manual Z workflow uses a
command the main controller firmware does not implement, and the manual
bed workflow lifts the nozzle to 15mm at every point; both workflows
keep the calibrated height here.

The pages follow the look of the stock display (`style.py`): its
palette, the card gradients, the orange primary and outlined secondary
buttons, the section list with the white indicator and the dp sizes of
the j1 layouts, scaled from the 432dp stock page height to the
KlipperScreen content area.  The style applies to the calibration
panel independent of the KlipperScreen theme; animations are scaled to
the stock picture size.

### KlipperScreen theme

`klipperscreen/snapmaker_j1/theme` is a KlipperScreen theme
(`snapmaker-j1`) with the same palette for all other panels: page and
card colors, rounded card tiles, the orange gradient for the chosen
option, orange outlines for selected items, the stock switches,
sliders and progress bars, dialogs with colored choices, toasts with a
colored edge, J1 graph colors and the Roboto font (install the
`fonts-roboto` package on the display module).  The icons are the
KlipperScreen material-dark set recolored to the J1 grey levels by
`theme/make_icons.py`.  KlipperScreen draws the print progress ring
in fixed colors; with this theme the add-on draws it as the stock
track with the orange gradient.  The install script links the theme
to `KlipperScreen/styles/snapmaker-j1` and selects it in
KlipperScreen.conf; another theme can still be chosen in the
KlipperScreen settings.

The menu of the J1 comes from `snapmaker_j1/snapmaker_j1.conf`, which
the install script includes from KlipperScreen.conf: the calibration
entry, and the generic Bed Level, Bed Mesh, Z Calibrate and Input
Shaper panels hidden (the J1 calibration menu covers them; the J1 has
no accelerometer).  The add-on hides the shutdown button of the action
bar (the J1 is switched off with its power switch; the emergency stop
still shows while printing) and names the nozzles "Left Nozzle" and
"Right Nozzle".  The printer config names the other devices for the
screen (`left_part_fan`, `right_part_fan`, `left_hotend_fan`,
`right_hotend_fan`, `board_fan`, `case_light`, shown as "Left Part
Fan" and so on); the main board power switches start with an
underscore (`_heater_power`, `_bed_power`, `_motor_power`,
`_screen_power`), which hides them in KlipperScreen.

Installation (on the display module):
```
./install.sh --apk base.apk --images ~/Animations
```
This links `klipperscreen/snapmaker_j1` as a KlipperScreen
add-on, enables add-ons, adds the "Calibration" main menu entry and
copies the pictures to `~/printer_data/config/snapmaker_j1/images` and
the three test prints to `~/printer_data/gcodes/snapmaker_j1/`.  The
pictures and test prints belong to Snapmaker and are not part of this
repository; `scripts/snapmaker_j1_extract_assets.py` takes them from
the display application of the user's own printer
(`/data/app/com.snapmaker.j1-*/base.apk` on the userdata partition).
Pictures given with `--images` take precedence.

### Commands

The same workflows are available as macros without the touch screen:
`SNAPMAKER_CALIBRATE_Z [POINT=]`, `SNAPMAKER_BED_LEVEL`,
`SNAPMAKER_CALIBRATE_NOZZLE_HEIGHT` and `SNAPMAKER_CALIBRATE_XY`.  The
individual steps are `SNAPMAKER_CAL_BEGIN`, `SNAPMAKER_CAL_HEAT
[WAIT=1]`, `SNAPMAKER_CAL_CLEAN_POSITION`, `SNAPMAKER_CAL_MOVE POINT=
[TOOL=] [Z=] [KEEP_Z=1]`, `SNAPMAKER_CAL_JOG DISTANCE=`,
`SNAPMAKER_CAL_DATUM POINT=`, `SNAPMAKER_CAL_HEIGHT POINT= TOOL=`,
`SNAPMAKER_CAL_SET_ORIGIN`, `SNAPMAKER_CAL_XY`,
`SNAPMAKER_CAL_NOZZLE_OFFSET X_ADJUST= Y_ADJUST=` and
`SNAPMAKER_CAL_END SAVE=0|1`.  Points 0-5 are the stock calibration
points (bed center, rear center, front left, front right, rear left,
rear right), corrected by the bed center offset measured by the XY
calibration.

`SNAPMAKER_SET_PLATE_THICKNESS THICKNESS=` (4.7-5.5mm, default 5.0)
shifts the Z origin when a build plate of another thickness is used.
`SNAPMAKER_SET_VIBRATION_FREQ AXIS= FREQ=` stores an input shaper
frequency.

## G-code compatibility

The macros accept the Snapmaker and Marlin commands found in J1 slicer
profiles and the display's calibration prints: `T0`/`T1`, `M104`/`M109`
with `T`, `M190 R`, `M106`/`M107` with `P`, `M201`, `M203`, `M204`
(limited by the noise mode), `M205 V`, `M355`, `M593`, `M600`, `M605
S0-S4`, `M900`, `M906` (with `I1` for X2), `M1999`, `M2000 S111/S113/
S200/S6/S7` and `G1029` (reports the replacement commands).

## Open items

* Validation on the printer: clock and UART on the real board, the TMC
  mux states, sensor polarities, the filament sensor thresholds, the
  PT100 table and the mains failure hold-up time of the display module.
* A Linux tool for updating the firmware through the factory
  bootloader (protocol summarized above).
* Klipper host platform on the display module (Linux image for the
  SC20-W), planned in
  [klipper-snapmaker-j1-os](https://github.com/Nimrasol/-klipper-snapmaker-j1-os).
