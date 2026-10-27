# Klipper for the Snapmaker J1

<p align="center">
<img src="docs/img/klipper-snapmaker-j1.png" width="900" alt="Snapmaker J1 running Klipper">
</p>

**Your Snapmaker J1 with Klipper — on its own touch screen, with the J1
calibrations you know.**

KlipperSnapmakerJ1 replaces the stock firmware of the Snapmaker J1 IDEX
printer with [Klipper](https://github.com/Klipper3d/klipper).  The display
of the printer keeps working as its touch screen: it runs Klipper,
Moonraker and KlipperScreen in the look of the stock display, with the
guided calibrations, the pictures and the animations of the J1.  No extra
Raspberry Pi, no extra screen, no wiring.

<p align="center">
<img src="docs/manual/main-menu.png" width="860" alt="Main menu on the J1 touch screen">
</p>

## Why Klipper on the J1

- **Everything you had, on the screen you know.** Printing, temperature,
  move, extrude, light, fans and the J1 calibrations, in the colors of the
  stock display.
- **All the Klipper features.** Input shaping, pressure advance, macros,
  the console, the configuration in plain text files, and the large
  Klipper community.
- **A web interface.** Mainsail in every browser of your network: watch
  and control prints, upload files, edit the configuration.
- **Your slicer profiles keep working.** Files sliced with the J1
  profiles (for example in OrcaSlicer) print without changes, in every
  IDEX mode.
- **Updates with one tap.** Klipper, Moonraker, KlipperScreen and the J1
  support update from the screen or the browser.
- **The way back stays open.** The stock firmware can be installed again.

## A closer look

### Guided calibration, as on the stock display

All J1 calibrations are there, with the pictures and animations of the
stock display: heated bed leveling, Z offset, XY offset (assisted with the
calibration probe, or manual with a test print), the offset check,
vibration compensation, PID tuning and the build plate thickness.  The
results are stored at once, without a restart.

<table>
<tr>
<td><img src="docs/manual/cal-menu-z.png" width="420" alt="Calibration menu"></td>
<td><img src="docs/manual/bed-5-right-ok.png" width="420" alt="Bed leveling with the live height indicator"></td>
</tr>
<tr>
<td>The calibration menu: every workflow with its description</td>
<td>Live height indicator: turn the wheel until the green tick shows</td>
</tr>
</table>

### Two toolheads, all IDEX modes

Full control, duplication, mirror and backup mode, taken from the print
file.  Both nozzles are checked against the file before the print
starts.

<table>
<tr>
<td><img src="docs/manual/print-file.png" width="420" alt="Print file details"></td>
<td><img src="docs/manual/nozzle-check.png" width="420" alt="Nozzle diameter check"></td>
</tr>
<tr>
<td>Print files with thumbnail and slicer data</td>
<td>Nozzle check before the print</td>
</tr>
</table>

### Filament and power loss

Filament sensors on both toolheads with the runout and change dialog,
loading and unloading from the screen, and the recovery of a print
interrupted by a power loss.

<table>
<tr>
<td><img src="docs/manual/filament-change.png" width="420" alt="Filament change"></td>
<td><img src="docs/manual/power-loss.png" width="420" alt="Power loss recovery"></td>
</tr>
<tr>
<td>Filament runout and change</td>
<td>Resume after a power loss</td>
</tr>
</table>

### In the browser

<p align="center">
<img src="docs/manual/web-dashboard.png" width="860" alt="Mainsail dashboard">
</p>

Mainsail runs on the printer: open `http://snapmaker-j1.local`.  The
dialogs of the printer appear there too, and the slicer uploads and
starts prints directly.

**See every screen in the [user manual](docs/Manual.md).**

## Download

> **In preparation.** The installation package for the USB stick is not
> released yet.  It will be published on the
> [releases page](https://github.com/Nimrasol/KlipperSnapmakerJ1/releases/latest).

| File | Content |
| --- | --- |
| *coming soon* | installation package for the USB stick: display system and main controller firmware |
| *coming soon* | stock firmware package, to return to the stock firmware |

## Installation

> **In preparation.** The steps below describe the planned installation
> from a USB stick.  Until the package is released, the installation
> needs the EDL mode of the display module and a Linux computer, see the
> [installation of KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os/blob/main/docs/INSTALL.md).

1. **Download** the installation package from the
   [releases page](https://github.com/Nimrasol/KlipperSnapmakerJ1/releases/latest)
   and copy it to a USB stick (FAT32).
2. **Insert the stick** into the USB port on the front of the J1 and
   start the update on the stock touch screen.
3. **Wait** until the printer restarts.  The Klipper main menu appears on
   the touch screen.
4. **Connect to your network** under **More → Network**.  The printer is
   then reachable at `http://snapmaker-j1.local`.
5. **Calibrate** in the **Calibration** menu, in the order of the
   [user manual](docs/Manual.md#calibration): bed leveling, Z offset,
   XY offset, offset check.

### Back to the stock firmware

*In preparation:* the stock firmware package installs the stock system
again the same way, from a USB stick.

## Status

**Version 1.0.0** ([changelog](CHANGELOG.md)).  Runs on the J1 (board revision 2), with Klipper, Moonraker and
KlipperScreen on the display module: printing, the calibration menu and
the filament handling on the touch screen, and Mainsail in the browser.
The open items are listed in the
[technical documentation](docs/Snapmaker_J1.md#open-items).

## Documentation

| Document | Content |
| --- | --- |
| [User manual](docs/Manual.md) | every screen and menu, the calibration workflows step by step, the web interface |
| [Technical manual](docs/Technical.md) | components, installing on your own Klipper host, firmware build, updates, compatibility |
| [Snapmaker_J1.md](docs/Snapmaker_J1.md) | hardware, how each stock function is implemented in Klipper, open items |
| [KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os) | the Linux system of the display module, which runs Klipper, Moonraker, KlipperScreen and Mainsail on the printer |
| [Nimrasol/klipper](https://github.com/Nimrasol/klipper/tree/j1), branch `j1` | the main controller support (GD32F305, J1 factory bootloader) as Klipper commits, for reference and review |

## License

GNU GPLv3, see [LICENSE](LICENSE), like Klipper and KlipperScreen.
