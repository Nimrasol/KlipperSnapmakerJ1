#!/usr/bin/env python3
# Extract the calibration pictures and test prints of the Snapmaker J1
# display application for local use by the calibration menu
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import sys, os, re, zipfile, argparse

# The pictures (klipperscreen/snapmaker_j1/images) and test prints
# (gcodes/) of this repository were taken with this tool; it renews them
# from another version of the display application
# (/data/app/com.snapmaker.j1-*/base.apk), eg
#   snapmaker_j1_extract_assets.py base.apk --gcodes gcodes #       --images klipperscreen/snapmaker_j1/images
IMAGES = [
    'gif_calibration_j1_heated_bed_leveing_auxiliary_content',
    'gif_calibration_j1_xy_offset_auxiliary_calibration_content',
    'gif_calibration_j1_xy_offset_restore_machine',
    'gif_calibration_j1_z_offset_calibration_content',
    'gif_calibration_j1_z_offset_clean_nozzies',
    'gif_calibration_j1_z_offset_heat_noaales_and_bed',
    'gif_calibration_j1_z_offset_lossen_screws',
    'gif_calibration_j1_z_offset_tighten_the_screws',
    'gif_calibration_j1_z_offset_tighten_the_screws_and_glass_plate',
    'gif_j1_calibration_check_printing',
    'gif_j1_calibration_print_calibration_model',
    'gif_leveling_bed_auxiliary_calibration_info',
    'gif_leveling_xy_calibration_content',
    'pic_calibration_j1_z_offset_load_filament_for_vibration',
    'pic_leveling_bed_calibration_auxiliary_left_point_content',
    'pic_leveling_bed_calibration_auxiliary_right_point_content',
    'pic_leveling_z_calibration_auxiliary_content',
    'pic_j1_calibration_check_for_z_offset',
    'pic_j1_calibration_check_for_xy_offset',
    'pic_calibration_j1_z_offset_load_filament',
    'pic_model_check_360x408',
    'pic_calibration_j1_clibration_vibration_content',
    'ic_j1_calibration',
    'pic_j1_calibration_vibration',
    'pic_j1_calibration_vibration_model',
    # Height indicator: direction to turn the wheel, bar out of view
    'icon_calibration_clockwise',
    'icon_calibration_anti_clockwise',
    'icon_tips_success_64x64',
    'pic_slide_indicator_left',
    'pic_slide_indicator_right',
    # Thumbs up of the success page
    'pic_like_160x160',
    # Filament runout and change dialog
    'pic_warning_filament_runout_120x120',
]
# Test prints: calibration check, vibration compensation.  The XY test
# lines of the application (a400_xy) are made for the larger A400 bed;
# the manual XY calibration uses a test print sliced by the user.
GCODES = {
    'scp_p4': 'snapmaker_calibration_check.gcode',
    'gcode_vibration_compensation_print': 'snapmaker_vibration_test.gcode',
}
DENSITY_ORDER = ['xxxhdpi', 'xxhdpi', 'xhdpi', 'hdpi', 'mdpi', '']

def density_rank(path):
    folder = path.split('/')[-2]
    for i, density in enumerate(DENSITY_ORDER):
        if density and density in folder:
            return i
    return len(DENSITY_ORDER)

# Travel limits per tool (X, Y).  The stock firmware clamps moves to its
# soft endstops and the calibration check parks the carriages just
# beyond them (X-14, X340) and wipes at Y-0.5; Klipper rejects such
# moves, so travel moves are clamped here.  X of the right carriage stays
# below the lowest plausible calibrated endstop.
TRAVEL_LIMITS = {0: ((-13., 324.), (0., 202.)), 1: ((0., 337.), (0., 202.))}

def adapt_gcode(data):
    # Travel moves clamped as above; G28 of the start G-code homes only
    # when needed, as the stock firmware does at the start of a print (the
    # calibration menu has homed the printer already).  The G28 of the end
    # G-code stays: it parks the carriages and lowers the bed.
    out = []
    tool = 0
    relative = False
    started = False
    for line in data.splitlines(True):
        code = line.split(b';')[0].strip()
        if line.startswith(b';LAYER:'):
            started = True
        if code.startswith(b'G28') and not started:
            ending = line[len(line.rstrip(b'\r\n')):]
            line = b'SNAPMAKER_HOME_IF_NEEDED' + ending
        elif code in (b'T0', b'T1'):
            tool = int(code[1:])
        elif code.startswith(b'G91'):
            relative = True
        elif code.startswith(b'G90'):
            relative = False
        elif (re.match(br'G0?[01]\s', code) and not relative
              and b'E' not in code):
            for i, axis in enumerate((b'X', b'Y')):
                low, high = TRAVEL_LIMITS[tool][i]
                def clamp(m):
                    value = min(max(float(m.group(1)), low), high)
                    return axis + (b'%g' % (value,))
                line = re.sub(axis + br'(-?\d+\.?\d*)', clamp, line, count=1)
        out.append(line)
    return b''.join(out)

def main():
    parser = argparse.ArgumentParser(
        description="Extract Snapmaker J1 calibration assets from base.apk")
    parser.add_argument("apk", help="J1 display application (base.apk)")
    parser.add_argument("--images", help="output directory for pictures")
    parser.add_argument("--gcodes", help="output directory for test prints")
    parser.add_argument("--skip-existing", action="store_true",
                        help="keep pictures already in the output directory")
    args = parser.parse_args()
    apk = zipfile.ZipFile(args.apk)
    names = apk.namelist()
    if args.images:
        os.makedirs(args.images, exist_ok=True)
        for image in IMAGES:
            pattern = re.compile(r'^res/drawable[^/]*/%s\.(png|gif|webp)$'
                                 % (image,))
            found = sorted([n for n in names if pattern.match(n)],
                           key=density_rank)
            if not found:
                sys.stderr.write("Missing picture %s\n" % (image,))
                continue
            ext = found[0].rsplit('.', 1)[1]
            dest = os.path.join(args.images, "%s.%s" % (image, ext))
            if args.skip_existing and any(
                    os.path.exists(os.path.join(args.images, image + '.' + e))
                    for e in ('gif', 'png', 'webp')):
                continue
            with open(dest, 'wb') as f:
                f.write(apk.read(found[0]))
    if args.gcodes:
        os.makedirs(args.gcodes, exist_ok=True)
        for raw, filename in GCODES.items():
            data = adapt_gcode(apk.read('res/raw/%s.gcode' % (raw,)))
            with open(os.path.join(args.gcodes, filename), 'wb') as f:
                f.write(data)

if __name__ == '__main__':
    main()
