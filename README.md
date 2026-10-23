# KlipperSnapmakerJ1

Klipper support for the Snapmaker J1 IDEX printer: the printer specific
parts that stock [Klipper](https://github.com/Klipper3d/klipper),
[KlipperScreen](https://github.com/KlipperScreen/KlipperScreen) and
[Moonraker](https://github.com/Arksine/moonraker) do not provide.  Klipper
and KlipperScreen stay unmodified; this repository is linked into them and
updated on its own through the Moonraker update manager.

> **Status:** tested in simulation only (Klipper batch tests, KlipperScreen
> against a simulated J1).  It has not run on a printer yet; see
> [Open items](docs/Snapmaker_J1.md#open-items).

This project is not affiliated with or endorsed by Snapmaker.

## Related repositories

| Repository | Content |
| --- | --- |
| **KlipperSnapmakerJ1** (this one) | Klipper modules, printer configuration, KlipperScreen add-on and theme, main controller firmware patch |
| [KlipperSnapmakerJ1-os](https://github.com/Nimrasol/KlipperSnapmakerJ1-os) | Linux image for the J1 display module (Quectel SC20-W), the Klipper host |
| [Nimrasol/klipper](https://github.com/Nimrasol/klipper/tree/j1), branch `j1` | Klipper fork with the firmware changes (GD32F305, J1 factory bootloader) as commits on Klipper; the same changes as `firmware/klipper-gd32f305-snapmaker.patch`. The printer runs unmodified Klipper |

## Features

* **Main controller firmware** (GD32F305): chip support at 120MHz and the
  J1 factory bootloader (`firmware/`).  The firmware is built from stock
  Klipper with a small patch and installed from the display module
  through the factory bootloader, with the stock update protocol
  (`scripts/snapmaker_j1_flash.py`).
* **Klipper host modules** (`klippy/extras/`):
  * `snapmaker_j1`: hardware revision check, nozzle type detection, bed
    heater feedback, IDEX mode from the print file header
  * `snapmaker_j1_probe`: calibration probe on the carriage switches
    (bed, Z, XY and nozzle offsets)
  * `snapmaker_j1_filament_sensor`: filament motion sensors of both
    nozzles
  * `snapmaker_j1_power_loss`: power loss recovery
* **Printer configuration and macros** (`config/`): both toolheads with
  IDEX modes, fans, heaters, TMC2209 drivers, and the Snapmaker/Marlin
  g-code of the J1 slicer profiles.
* **KlipperScreen** (`klipperscreen/snapmaker_j1/`):
  * the J1 calibration menu with all eight workflows (bed leveling,
    Z offset, XY offset with and without assist mode, calibration
    check, vibration compensation) and the live height indicator
  * the `snapmaker-j1` theme after the stock display
  * the J1 menu: calibration entry, generic calibration panels and the
    shutdown button hidden, readable device names

## Installation

On the Klipper host, with Klipper, Moonraker and KlipperScreen installed:

```
cd ~
git clone https://github.com/Nimrasol/KlipperSnapmakerJ1.git
./KlipperSnapmakerJ1/install.sh --apk base.apk
sudo systemctl restart moonraker klipper KlipperScreen
```

`install.sh` links the host modules into Klipper, the configuration into
`~/printer_data/config/snapmaker_j1` (included from `printer.cfg`), the
add-on, theme and menu into KlipperScreen, and adds the update manager
entry to `moonraker.conf`.

The calibration pictures and test prints belong to Snapmaker and are not
part of this repository.  `--apk` takes them from the display application
of your own printer (`/data/app/com.snapmaker.j1-*/base.apk`).

### Main controller firmware

```
./KlipperSnapmakerJ1/firmware/build.sh
```

builds the firmware from the installed Klipper and writes `mc.bin`,
`update.bin` (stock display USB update), `klipper.bin` and
`boot-header.bin` (SWD) to `firmware/out`.  Install it with Klipper
stopped:

```
~/klippy-env/bin/python ~/KlipperSnapmakerJ1/scripts/snapmaker_j1_flash.py     ~/KlipperSnapmakerJ1/firmware/out/mc.bin
```

The factory bootloader checks the image and writes only the application
pages; an interrupted update is completed by running the script again,
and a stock `mc.bin` returns to the stock firmware.  Rebuild and install
the firmware when a Klipper update changes the protocol to the main
controller.

## Updates

Updates of this repository appear in the update panel of KlipperScreen,
Mainsail and Fluidd (`[update_manager KlipperSnapmakerJ1]`).  Klipper,
Moonraker and KlipperScreen stay unmodified clones of their own
repositories and are updated through their own entries, but only up to
the versions this release is tested with: KlipperSnapmakerJ1 pins them
in the update manager.  A release with newer tested versions moves the
pins, so update KlipperSnapmakerJ1 first and then the others.

## Compatibility

This release is tested with ([versions.conf](versions.conf)):

| Component | Version | Date |
| --- | --- | --- |
| Klipper | v0.13.0-809-gc63b2951 | 2026-10-18 |
| Moonraker | v0.11.0-3-g9e676eb | 2026-09-28 |
| KlipperScreen | v0.4.7-198-g911c75b | 2026-10-18 |

The update manager offers updates only up to these versions; see
[Compatibility](docs/Snapmaker_J1.md#compatibility) for what depends on
each version.

## Documentation

[docs/Snapmaker_J1.md](docs/Snapmaker_J1.md): hardware, the mapping of
every stock function to Klipper, the calibration menu, building and
installing, and the open items.

## License

GNU GPLv3, see [LICENSE](LICENSE), like Klipper and KlipperScreen.
