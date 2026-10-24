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
* Host link: USART2 remapped to PD5 (TX) / PD6 (RX), connected to the
  display module (`/dev/ttyMSM1` with the mainline kernel of
  KlipperSnapmakerJ1-os, `/dev/ttyHSL1` with the stock Android kernel).
  The stock firmware enables its display
  protocol on this port (`event_serial[EVENT_SOURCE_HMI]`, the second
  serial port), and the factory bootloader fetches stock updates through
  it.  USART1 (PB6/PB7) carries the Marlin console and the bootloader's
  text messages.  The stock firmware uses 115200 baud, Klipper 230400.

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
| 81 | status (0xAA01 waiting, 0xAA02 update requested, 0xAA03 updating, 0xAA04 update done, 0xAA05 application normal) |
| 83 | application length |
| 87 | application checksum |
| 91 | application start (2KiB aligned, at least 0x08002800) |
| 95 | port to fetch the image from (0 USART1, 1 USART2) |
| 96 | SACP id to fetch the image from (2 display) |
| 97 | header checksum over bytes 0-96 |

Checksums are the inverted 32 bit sum of the big-endian 16 bit words.
The bootloader (V1.0.3-boot) listens on USART1 and USART2 at 115200
baud and works with the status:

* 0xAA05 and a matching application checksum: it waits 6 seconds for a
  new header, then starts the application.
* 0xAA02: it erases the application pages given by the header, sets
  0xAA03 and requests the image from the port and id in the header.
* After the last byte (0xAA04) it checks the application checksum,
  reports the result and starts the new application; the application
  restores 0xAA05.  A failed check, an invalid header or an interrupted
  update (5 unanswered requests) leave it waiting for a new header.

Updates use the SACP protocol (frame `AA 55 len16 ver dst crc8 src attr
seq16 set id data sum16`, CRC-8 polynomial 0x07 over the first 6 bytes,
inverted 16 bit word sum over the rest): the bootloader or the stock
firmware accepts a new header (command set 0xAD, id 0x01, data: length
and the 256 header bytes) after checking its checksum, image type, start
address and length, stores it with 0xAA02 and starts the update; it
requests 2KiB chunks by byte offset (0xAD/0x02, answered with result,
offset, length and data) and reports the result (0xAD/0x03).  The
bootloader only erases and writes the pages of the application and the
header, never its own.

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
| Bed heater | PA10 | solid state relay (high = on), feedback !PA12 (low = powered) |
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
| Noise modes (normal/silent/loud) | `SET_VELOCITY_LIMIT` (200/8000, 75/3000, 300/8000), `SET_TMC_FIELD en_spreadcycle` | macros |
| Input shaping (M593) | `[input_shaper]` per carriage | macros |
| Linear advance (M900) | pressure advance | macros |
| PT100 hotend sensors | `[adc_temperature]` from the stock table | none |
| Thermal protection | `[verify_heater]`, min/max temp (5-320C nozzles, 5-110C bed) | none |
| Highest heater target (MAXTEMP - OVERSHOOT: 300C nozzles, 100C bed) | `M104`/`M109`/`M140`/`M190`/`SET_HEATER_TEMPERATURE` limit the target | macros |
| Heater supply switches cut on errors | `[output_pin]` with `shutdown_value: 0` | none |
| Bed relay self check | continuous feedback monitoring of PA12 | `snapmaker_j1` |
| Board revision detection | ADC check against the configured revision | `snapmaker_j1` |
| Nozzle type detection | ADC classification, `SNAPMAKER_QUERY_HARDWARE` | `snapmaker_j1` |
| Nozzle diameter check before a print ("Inconsistent Nozzle Diameter") | `SNAPMAKER_CHECK_NOZZLES` from `SDCARD_PRINT_FILE`, `action:prompt` dialog | `snapmaker_j1` |
| Missing hotend ("nozzle loss") | `max_temp` shutdown, message names the undetected nozzle | `snapmaker_j1` |
| Fans (part, hotend, electronics) | `fan_generic`, `heater_fan`, `temperature_fan` | none |
| Case light (M355) | `[output_pin]` | macros |
| Nozzle contact probing (Z) | probe interface using the active nozzle's switch | `snapmaker_j1_probe` |
| Calibration touches (fast touch, slow touches, switch opening point, trimmed mean) | stock sequence on the probe switch | `snapmaker_j1_probe` |
| StallGuard crash detection while probing | DIAG line armed with the nozzle switch on one trsync, thresholds from SG_RESULT | `snapmaker_j1_probe` |
| Z offset calibration | `PROBE` + `SNAPMAKER_Z_ENDSTOP_ADJUST` | `snapmaker_j1_probe` |
| Heated bed leveling (knobs) | `[screws_tilt_adjust]` | none |
| XY offset calibration of T1 | horizontal probing of the bed center feature | `snapmaker_j1_probe` |
| T1 nozzle height adjustment | `SNAPMAKER_NOZZLE_HEIGHT` | `snapmaker_j1_probe` |
| Build plate thickness | Z origin shift, setting in the calibration menu | `snapmaker_j1_probe` |
| Analog filament runout/jam detection | motion sensor based on the analog reading | `snapmaker_j1_filament_sensor` |
| Pause / resume with parking, priming and wiping | `PAUSE`/`RESUME` macros, `SAVE_DUAL_CARRIAGE_STATE` | macros |
| Power loss detection and recovery | state checkpoints, shutdown, `M23`/`M26`/`M24` resume | `snapmaker_j1_power_loss` |
| Factory bootloader boot state | restore "application normal" at startup | MCU |
| Firmware update via the display | `scripts/snapmaker_j1_package.py`, `scripts/snapmaker_j1_flash.py` (stock update protocol to the factory bootloader) | script |
| Calibration menu and workflows | KlipperScreen add-on | add-on |

Not ported: the SACP display protocol (the stock display application
cannot control Klipper), CNC/laser functions of the shared display code,
the optional StallGuard check of Z homing (`M2000 S14`, off by default
in the stock firmware) and the simultaneous T0/T1 parking move of
`M2000 S200` (tool changes park the inactive carriage first).

### Limits

The limits come from the stock firmware (SnapmakerController-IDEX, its
defaults are byte identical in the firmware of a J1's main controller)
and, where the values stored on a J1 are lower (M503), from those:

| Limit | Stock | Klipper |
| --- | --- | --- |
| Steps per mm X/Y/Z/E | 80 / 80 / 1600 / 138.58 | `rotation_distance` 40 / 40 / 2 / 23.091 |
| Travel T0, T1, Y | X -13..324, X2 0..337 (home 337), Y 0..202 | same |
| Z | homes up, soft minimum about 9.5mm below the plate surface (home offset) | `position_min: -8` (the calibrations probe the bare bed) |
| Velocity X/Y/Z | 350 / 300 / 10 mm/s (stored) | `max_velocity: 300`, `max_z_velocity: 10` |
| Acceleration X/Y/Z | 10000 / 8000 / 100 mm/s^2 (stored) | `max_accel: 8000`, `max_z_accel: 100` |
| Extruder only | 40 mm/s (stored), 6000 mm/s^2, 200mm, 170C minimum | same |
| Motor current | X 1000, Y 1400, Z 1000, E 800 mA RMS, 0.15 ohm | same; hold current not reduced (Klipper's recommendation) |
| Heaters | target up to 300C / 100C, shutdown 320C / 110C, fault below 5C | same (macros limit the target) |
| Homing | 50 / 50 / 10 mm/s, second touch a tenth, 2mm back off | same |


## Klipper changes

### MCU

* `MACH_GD32F305`: stm32f105 "connectivity line" register set with the
  120MHz clock tree above, Cortex-M4 code generation.
* `STM32_FLASH_START_2800`: 10KiB bootloader offset.
* `STM32_SNAPMAKER_BOOTLOADER` (`src/stm32/snapmaker_boot.c`): at
  startup it rewrites the update header status to 0xAA05 when it is not
  set (as the stock firmware does); a bootloader request resets into the
  factory bootloader, which waits 6 seconds for a new image.

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
mode from the file header; `SNAPMAKER_CHECK_NOZZLES FILENAME=<file>`
compares the nozzle diameters of a file with the installed nozzles.
Status: `hardware_version`, `detected_hardware_version`, `nozzle_t0`,
`nozzle_t1` (`material`, `diameter`, `adc_mv`), `nozzle_check`
(`filename`, `mismatch`, `file`, `machine`), `bed_feedback`.

Like the stock display, `SDCARD_PRINT_FILE` asks before printing a file
made for other nozzle diameters.  The diameters come from the header
(`;Extruder 0 Nozzle Size:` of the J1 profiles, `;nozzle_0_diameter(mm):`,
Cura's `;EXTRUDER_TRAIN.0.NOZZLE.DIAMETER:`) or from the slicer settings
at the end of the file (`; nozzle_diameter = 0.4,0.4` of PrusaSlicer and
OrcaSlicer); a tool without a diameter in the file is not checked, an
undetected nozzle counts as a mismatch.  The dialog uses Klipper's
`action:prompt` protocol, so KlipperScreen, Mainsail and Fluidd show it:
"Cancel" (`_SNAPMAKER_NOZZLE_CANCEL`) or "Continue Anyway"
(`_SNAPMAKER_NOZZLE_CONTINUE`, prints the file).
`SDCARD_PRINT_FILE FILENAME=<file> NOZZLE_CHECK=0` prints without the
check (the calibration prints, as in the stock firmware).

A missing hotend opens its temperature sensor and shuts Klipper down
(`max_temp`, "ADC out of range"); the shutdown message then starts with
"Nozzle L/R not detected - check that the hotend is installed and its
cable is plugged in" (stock: "nozzle loss" exception).

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
#z_probe_distance: 30
#z_probe_speed: 5
#z_probe_slow_speed: 0.5
#z_live_speed: 1.25
#xy_probe_distance: 15
#xy_probe_speed: 13.333
#xy_probe_slow_speed: 1.333
#probe_backoff: 1
#probe_max_delta: 0.25
#probe_samples: 5
#   Calibration touches (stock calibtration.cpp): one fast touch over
#   up to the probe distance, then probe_samples slow touches starting
#   probe_backoff above the surface, each reaching 2 * probe_max_delta
#   further (twice that for the first slow touch).  The live height
#   measurement uses z_live_speed for its slow touches.
#max_t1_offset: 5
#max_center_offset: 5
#plate_thickness: 5
#   Thickness of the build plate in mm: Z 0 is this much above the bed
#   surface the calibrations measure. Set by
#   SNAPMAKER_SET_PLATE_THICKNESS (and the calibration menu) through
#   SAVE_CONFIG.
#stallguard_pin_stepper_x:
#stallguard_pin_dual_carriage:
#stallguard_pin_stepper_y:
#stallguard_pin_stepper_z:
#   DIAG (StallGuard) outputs of the drivers. Revision 2 boards: PD12,
#   PE3, PB5, PE9; revision 1 boards: !PE3 for all four. Without these
#   pins the fast touches run unguarded.
#stallguard_measure: True
#   Derive the thresholds from SG_RESULT during the first travel moves
#   after a restart (stock: Z SG_RESULT/3 - 25 above 3mm/s, Y /10, X /12
#   above 50mm/s).
#stallguard_threshold_stepper_x: 20
#stallguard_threshold_dual_carriage: 20
#stallguard_threshold_stepper_y: 20
#stallguard_threshold_stepper_z: 80
#   Fixed SGTHRS values (no measurement for this driver). Unset, the
#   stock defaults apply until a measurement replaces them.
```

The module registers as the printer `probe` and uses the switch of the
active carriage (the other carriage is parked first).  Besides the
calibration session commands (see Calibration) it provides
`SNAPMAKER_PROBE_XY_CENTER [TOOL=] [Z=]`,
`SNAPMAKER_Z_ENDSTOP_ADJUST OFFSET=` (moves the Z origin up by OFFSET,
updating `position_endstop` and `position_max` of `[stepper_z]`) and
`SNAPMAKER_QUERY_STALLGUARD` (thresholds, their source and the DIAG
line states).  The descent for XY probing is a probing move: a nozzle
contact before reaching the calibration height aborts with a request to
remove the build plate.  Status: `calibration` (`active`, `datum`,
`height_difference`, `height_valid`, `z_origin_offset`, `t1_offset`,
`bed_center_offset`) and `stallguard` (`threshold`, `sg_result` per
driver) in addition to the probe status.

Calibration touches follow the stock firmware: the nozzle approaches
until its switch closes, then moves back until the switch opens; the
opening position is the result.  A measurement takes one fast touch
(discarded) and five slow ones and averages them without the highest
and lowest.  Only the regular probe commands (`PROBE`, `BED_MESH`, ...)
use Klipper's trigger position.

During the fast touch the DIAG line of the moving driver (Z, Y or the
active X carriage) is armed together with the nozzle switch on the same
trsync, with `SGTHRS` set and `TCOOLTHRS`/StealthChop enabled for that
driver only.  A stall stops the move at once and aborts the calibration
with "StallGuard stopped the ... axis"; the axis must be homed again (as
in the stock firmware).  A DIAG line that is already active before the
move (driver error) is logged and the touch runs without StallGuard.

#### [snapmaker_j1_filament_sensor]

```
[snapmaker_j1_filament_sensor my_sensor]
adc_pin:
extruder:
#check_distance: 3
#threshold:
#   Minimum change of the normalized reading per check_distance of
#   extrusion. The default follows hardware_version of [snapmaker_j1]
#   as in the stock firmware: 15/4096 on revision 2 boards, 8/4096 on
#   revision 1.
#check_count: 3
#   Consecutive checks without motion that report a runout or jam.
#dead_space_min:
#dead_space_max:
#   Readings outside this range are "dead space" where the sensor
#   changes little (revision 2: 60/4096 and 4060/4096, revision 1: 0
#   and 1433/4096).
#dead_space_checks: 2
#   Additional checks before a runout in the dead space (stock: 4mm in
#   steps of its 2mm setting).
#pause_on_runout, runout_gcode, insert_gcode, event_delay, pause_delay:
#   See the "filament_switch_sensor" section.
```

The sensors check while the toolhead moves; a runout only acts while a
print runs (`_SNAPMAKER_FILAMENT_RUNOUT`): the print pauses when the
sensor of a printing toolhead reports it, in backup mode the print
continues on the other toolhead once.  `SET_FILAMENT_SENSOR` and the
stock `M412 S<0|1> T<0|1>` switch a sensor; the state is kept in the
save_variables file (`snap_j1_<name>_enabled`) like the stock EEPROM
setting.  `RESUME` and `SNAPMAKER_POWER_LOSS_RESUME` prime the
toolheads and refuse to continue when an enabled sensor of a printing
toolhead saw no filament motion (stock: power loss resume).  The
KlipperScreen add-on shows both sensors with their switch in the
extrude panel.

When a print pauses for a runout or an `M600` filament change, the
macros store the toolhead in `_SNAPMAKER_STATE` (`runout_tool`,
`runout_reason`) and the add-on opens the stock refill dialog instead
of the extrude panel: unload, insert the filament, heat and feed 100mm
at 240mm/min (stock), then "Continue Printing" (`RESUME`) or load again.
In duplication and mirror mode the dialog selects the toolhead and only
that extruder moves.  `LOAD_FILAMENT` and `UNLOAD_FILAMENT [TOOL=<0|1>]
[TEMP=<°C>] [LENGTH=<mm>] [SPEED=<mm/min>]` use the active toolhead and
the print temperature by default (220°C below 170°C); they are also
used by the load/unload buttons of the KlipperScreen extrude panel.

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

## Compatibility

Releases are tagged `vX.Y.Z` (the update manager shows this version).
Each release is made and tested with the versions listed in its
[versions.conf](../versions.conf); for this release:

| Component | Version | Commit | Date |
| --- | --- | --- | --- |
| [Klipper](https://github.com/Klipper3d/klipper) | v0.13.0-816-gee2c6fb6 | `ee2c6fb6` | 2026-10-21 |
| [Moonraker](https://github.com/Arksine/moonraker) | v0.11.0-4-gb559b9a | `b559b9a8` | 2026-10-21 |
| [KlipperScreen](https://github.com/KlipperScreen/KlipperScreen) | v0.4.7-198-g911c75b | `911c75bf` | 2026-10-18 |
| [KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os) | Debian 12 (bookworm) armhf, Python 3.11, lk2nd and Linux 6.12 (msm8916-mainline) | | |

What depends on each version, and how it was tested:

* **Klipper:** the firmware patch (`src/stm32`, applies to this commit)
  and the host modules, which use Klipper internals (`probe`,
  `dual_carriage`, the runout helper of `filament_switch_sensor`,
  `virtual_sdcard`, `configfile`, `save_variables`).  Tested with batch
  runs of the printer configuration, all calibration workflows, SD card
  printing and the power loss recovery; the firmware builds.
* **KlipperScreen:** the add-on interface (`addons/`, `_load_panel`), the
  base panel, `ScreenPanel.prettify` and the fan, pins and job status
  panels the add-on adjusts, and the theme files.  Tested with all
  calibration workflows and 71 pages of KlipperScreen against a simulated
  J1 (layout checks included).
* **Moonraker:** the update manager entry (pinned commits) and the
  systemd service provider of the image.  Tested in the user space test of the image
  (Moonraker connected to Klipper, all repositories valid and unmodified
  in the update manager).

The update manager keeps Klipper, Moonraker and KlipperScreen as clones of
their own repositories, but offers updates only up to the versions of
`versions.conf`: `moonraker/KlipperSnapmakerJ1.conf` sets
`pinned_commit` for their entries (written by
`scripts/snapmaker_j1_versions.py`; `--check` verifies it before a
release).  A release of KlipperSnapmakerJ1 with newer tested versions
moves the pins; Moonraker restarts after that update and then offers
Klipper, Moonraker and KlipperScreen up to the new versions.  A version
newer than the pin (installed by hand) is kept and not offered back.
After a Klipper update, rebuild and install the main controller firmware
when Klipper reports a protocol mismatch (`firmware/build.sh`, which also
names the tested version).

## Building and installing

On the Klipper host (the display module), with Klipper, Moonraker and
KlipperScreen installed:

1. Install this repository:
   ```
   cd ~
   git clone https://github.com/Nimrasol/KlipperSnapmakerJ1.git
   ./KlipperSnapmakerJ1/install.sh --apk base.apk
   ```
   This links the host modules into `~/klipper/klippy/extras`, the
   configuration into `~/printer_data/config/snapmaker_j1` (included
   from `printer.cfg`), the KlipperScreen add-on, theme and menu, and
   adds the Moonraker update manager entry.  The calibrated values
   (`position_endstop` and `position_max` of `[stepper_z]` and
   `[dual_carriage]`, `control` and the PID values of both nozzles and
   the bed) are written to `printer.cfg` itself with the stock defaults,
   because `SAVE_CONFIG` cannot change values of an included file.  They
   are values of the individual printer and stay out of this repository;
   `PID_CALIBRATE HEATER=extruder TARGET=220` (likewise `extruder1`, and
   `heater_bed` at 60) followed by `SAVE_CONFIG` measures and stores
   them.  Check
   `hardware_version` and the mains failure pin in the printer
   configuration.
2. Build and package the main controller firmware:
   ```
   ./KlipperSnapmakerJ1/firmware/build.sh
   ```
   The script applies `firmware/klipper-gd32f305-snapmaker.patch` (the
   GD32F305 chip option and the factory bootloader support) to a copy
   of the installed Klipper, builds it with
   `firmware/snapmaker-j1.config` (the options listed at the top of
   `printer-snapmaker-j1-2022.cfg`) and packages the result into
   `firmware/out`.
3. Install the firmware with Klipper stopped:
   ```
   sudo systemctl stop klipper
   ~/klippy-env/bin/python ~/KlipperSnapmakerJ1/scripts/snapmaker_j1_flash.py \
       ~/KlipperSnapmakerJ1/firmware/out/mc.bin
   sudo systemctl start klipper
   ```
   The script checks the image (header, checksums, start address after
   the bootloader, vector table), resets the main controller into its
   factory bootloader (Klipper's serial bootloader request; the stock
   firmware accepts the image itself) and sends the image the way the
   stock display does: the factory bootloader checks the header, erases
   and writes only the application pages and starts the new firmware
   after checking its checksum.  If the update is interrupted (power
   loss, closed connection) the main controller stays in its bootloader;
   run the script again.

   For the first installation, while the main controller still runs
   the stock firmware, connect its USB port (USART1 through a CH340) to
   any Linux computer, for example a Raspberry Pi, and run the same
   script there:
   ```
   python3 snapmaker_j1_flash.py -d /dev/ttyUSB0 -v mc.bin
   ```
   It restarts the stock firmware with `M1999` and installs the image
   through the factory bootloader, as Snapmaker's own USB update tool
   does (tested on a J1 with stock firmware 2.2.14, about 30 seconds).
   The USB port stays the recovery path: the bootloader listens there
   for 6 seconds after every power up, so when the firmware does not
   answer, start the script with `-w 60` and switch the printer off and
   on.  Alternatively `update.bin` on a USB stick with the stock
   display's firmware update from USB does the same.

Updates of this repository are offered by the Moonraker update manager
(KlipperScreen "Update", Mainsail, Fluidd).  When an update of Klipper
changes the protocol to the main controller, rebuild and install the
firmware.

The display module also powers the Klipper host when Klipper runs on
it; PD4 is therefore an initial pin of the firmware and never switched
off.  To return to the stock firmware, install a stock `mc.bin` or
`update.bin` with the same script (for example the cached package of
the stock display, `/data/data/com.snapmaker.j1/app_update/mc.bin`),
then the stock display image.

SWD (ST-Link etc.) is only needed when the bootloader itself is
damaged.  The bootloader cannot be recreated from Klipper or the stock
packages, so when using SWD:

* first read and keep 0x08000000-0x080027FF (bootloader and serial
  number) and 0x080F9800-0x080FFFFF (factory data, header, settings),
* never use "mass erase", "erase chip" or "full chip erase", and do not
  change the option bytes or the read protection,
* program `klipper.bin` at 0x08002800 and `boot-header.bin` at
  0x080FD000 with "erase sectors" (only the pages that are written).

## Calibration

The stock calibrations measure on the bare heated bed (build plate
removed) with both nozzles at 220C and the bed at 60C; the print
surface is the measured bed surface plus the build plate thickness.
Results are collected in a calibration session and only stored when the
calibration completes (`SNAPMAKER_CAL_FINISH SAVE=1`, then
`SAVE_CONFIG`); quitting discards them.  The calibration menu runs
`SAVE_CONFIG` itself, without KlipperScreen's confirmation dialog.  The
bed leveling stores the Z origin (`position_endstop` of `[stepper_z]`):
the bed homes to the Z endstop, and turning the leveling wheels changes
the nozzle height at that position.  The assisted Z offset calibration
sets the right nozzle with its thumbwheel only and stores nothing; the
manual one also takes the Z origin from the left nozzle and the
calibration card.

### Calibration menu (KlipperScreen)

The touch screen menu reproduces the stock "Calibration" page with its
five entries, plus a "Build Plate" entry for the plate thickness; the
first three can be switched between the assisted (sensor) and the
manual workflow ("Assist Mode"):

| Entry | Assisted workflow | Manual workflow |
| --- | --- | --- |
| Heated Bed Leveling | remove plate, heat, clean nozzles, rear reference, live height bar while turning the front left and front right wheels, restore | checklist, calibration card at the rear point, then the front wheels at the same height |
| Z Offset Calibration | remove plate, loosen the right extruder screws, heat, clean, live height bar while turning the right extruder thumbwheel, tighten and restore | checklist, calibration card with the left nozzle (sets the Z origin), then the right nozzle thumbwheel at the same height |
| XY Offset Calibration | remove plate, heat, clean, automatic probing of the bed center feature, restore | test print of X/Y line patterns, then entering the observed shift |
| Offset Calibration Check | plate check, load filament, check print, Z and XY evaluation pages | - |
| Vibration Compensation | plate check, load filament, test print with 80/65/50/35Hz areas, choice per axis | - |
| Build Plate | setting: plate thickness in 0.1mm steps (default 5.0mm, the PEI glass plate), saved with `SAVE_CONFIG` | - |

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
"Right Nozzle".  "More → Network Name" sets the host name the printer
announces as `<name>.local` (NetworkManager and avahi on the D-Bus,
allowed for the group `netdev`), so several printers in one network
get their own addresses.  The printer config names the other devices for the
screen (`left_part_fan`, `right_part_fan`, `left_hotend_fan`,
`right_hotend_fan`, `case_light`, shown as "Left Part Fan" and so on);
the main board power switches and the electronics fan start with an
underscore (`_heater_power`, `_bed_power`, `_motor_power`,
`_screen_power`, `_board_fan`), which hides them in KlipperScreen,
Mainsail and Fluidd.

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
`SNAPMAKER_CAL_DATUM POINT= [ORIGIN=0]`, `SNAPMAKER_CAL_HEIGHT POINT=
TOOL=`, `SNAPMAKER_CAL_SET_ORIGIN`, `SNAPMAKER_CAL_XY`,
`SNAPMAKER_CAL_NOZZLE_OFFSET X_ADJUST= Y_ADJUST=` and
`SNAPMAKER_CAL_END SAVE=0|1`.  Points 0-5 are the stock calibration
points (bed center, rear center, front left, front right, rear left,
rear right), corrected by the bed center offset measured by the XY
calibration.

`SNAPMAKER_CAL_DATUM` also sets the Z origin (bed reference plus plate
thickness) unless `ORIGIN=0` is given; like the stock firmware, the bed
leveling stores it and the nozzle height calibration does not.
Repeated `SNAPMAKER_CAL_HEIGHT` calls at the same point work like the
stock live measurement: the first touch is fast and StallGuard guarded,
the next ones are slow and only as long as the last change requires; a
bed that was lowered beyond that or raised into the nozzle is found
again with a fast touch.

`SNAPMAKER_SET_PLATE_THICKNESS THICKNESS=` (0-10mm, default 5.0, the
PEI glass plate) shifts the Z origin when a build plate of another
thickness is used; the calibrations measure the bare bed and put Z 0
this much above it.  The thickness (`plate_thickness` of
`[snapmaker_j1_probe]`) and the shifted Z origin are stored together by
`SAVE_CONFIG`, so they cannot get out of step.
`SNAPMAKER_SET_VIBRATION_FREQ AXIS= FREQ=` stores an input shaper
frequency.

## G-code compatibility

The macros accept the Snapmaker and Marlin commands found in J1 slicer
profiles and the display's calibration prints: `T0`/`T1`, `M104`/`M109`
with `T`, `M190 R`, `M106`/`M107` with `P`, `M201`, `M203`, `M204`
(limited by the noise mode), `M205 V`, `M355`, `M412`, `M593`, `M600`, `M605
S0-S4`, `M900`, `M906` (with `I1` for X2), `M1999`, `M2000 S111/S113/
S200/S6/S7` and `G1029` (reports the replacement commands).

## Open items

Verified on a J1 (board revision 2): clock (120 MHz) and UART to the
display module, firmware update through the factory bootloader, homing of
all axes, bed and both hotend heaters, PT100 readings, hotend and part
fans, chamber light, the TMC2209 UART multiplexer (each of the six drivers
addressed separately), noise modes, the nozzle diameter dialog, Klipper
host on the display module with touch screen and WLAN
([KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os)).
Still to be validated on the printer: the filament sensor thresholds,
the calibrations end to end and the mains failure hold-up time of the
display module.
