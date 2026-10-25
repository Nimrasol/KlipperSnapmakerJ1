# Snapmaker J1 calibration workflows for the KlipperScreen calibration menu
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.

# The menu and the step sequences follow the stock J1 display
# application.  Each step names a picture of the stock application (see
# scripts/snapmaker_j1_extract_assets.py), the g-code run when the step
# is shown (enter) and when it is left (leave).

# Step kinds
INFO = 'info'          # read and continue
CHECK = 'check'        # confirm a checklist before continuing
HEAT = 'heat'          # wait for the calibration temperatures
LIVE = 'live'          # repeated height measurement with an indicator
JOG = 'jog'            # move the nozzle up/down by hand
RUN = 'run'            # automatic step, continue when it finished
PRINT = 'print'        # print a test file
LOAD = 'load'          # load filament or start the test print
CHOICE = 'choice'      # choose one of the test print areas
OFFSET = 'offset'      # enter the right nozzle offset from a test print
SUCCESS = 'success'    # final page
PID = 'pid'            # PID autotune of a heater

# Heaters of the PID autotune and their temperatures: the stock firmware
# tunes the nozzles at 235C (it does not tune the bed)
PID_HEATERS = [('extruder', 235), ('extruder1', 235), ('heater_bed', 60)]

# Frequencies of the four areas of the vibration test print, in the
# order of the selection buttons
VIBRATION_FREQS = [80, 65, 50, 35]

GCODE_DIR = 'snapmaker_j1'

def _step(kind, title, text, image=None, **kw):
    s = {'kind': kind, 'title': title, 'text': text, 'image': image}
    s.update(kw)
    return s

def pid_heater_name(heater):
    return {'extruder': _("Left Nozzle"), 'extruder1': _("Right Nozzle"),
            'heater_bed': _("Heated Bed")}[heater]

def build():
    """Return (menu, flows). Built at runtime so texts are translated."""
    remove_glass = _step(
        INFO, _("Remove PEI Glass Plate"),
        _("Remove the PEI glass plate and put it in a safe place, then tap"
          " Next. If it is already removed, just tap Next."),
        'gif_leveling_bed_auxiliary_calibration_info',
        enter="SNAPMAKER_CAL_BEGIN", glass_warning=True)
    loosen_screws = _step(
        INFO, _("Loosen Screws"),
        _("Loosen the two screws on the right extruder by one turn with the"
          " H2.0 hex key, then tap Next."),
        'gif_calibration_j1_z_offset_lossen_screws')
    heat = _step(
        HEAT, _("Heat Nozzles and Bed"),
        _("The nozzles and the bed are heating up for cleaning and"
          " calibration..."),
        'gif_calibration_j1_z_offset_heat_noaales_and_bed',
        ready_text=_("The nozzles and the bed are hot. Tap Next to"
                     " continue."),
        enter="SNAPMAKER_CAL_HEAT", leave="SNAPMAKER_CAL_CLEAN_POSITION")
    clean = _step(
        INFO, _("Clean Nozzles"),
        _("Clean the outer surface of both nozzles with the wire brush until"
          " no residue is left, then tap Next.\n\nSlight oozing later on does"
          " not affect the calibration."),
        'gif_calibration_j1_z_offset_clean_nozzies')
    restore_glass = _step(
        RUN, _("Restore Machine"),
        _("If no further calibration follows, clean the heated bed and put"
          " the PEI glass plate back on."),
        'gif_calibration_j1_xy_offset_restore_machine',
        enter="SNAPMAKER_CAL_END SAVE=1", glass_warning=True)
    restore_z = _step(
        RUN, _("Restore Machine"),
        _("Tighten the two screws on the right extruder.\n\nIf no further"
          " calibration follows, clean the heated bed and put the PEI glass"
          " plate back on."),
        'gif_calibration_j1_z_offset_tighten_the_screws_and_glass_plate',
        enter="SNAPMAKER_CAL_END SAVE=1", glass_warning=True)
    success = _step(SUCCESS, _("Calibrated Successfully"), "",
                    'pic_like_160x160')
    install_glass = _step(
        INFO, _("PEI Glass Plate Check"),
        _("Make sure the PEI glass plate is installed on the heated bed."),
        'gif_calibration_j1_xy_offset_restore_machine',
        enter="SNAPMAKER_CAL_PRINT_PREPARE", glass_warning=True)

    def load(image):
        return _step(
            LOAD, _("Load Filament"),
            _("Tap Go to Load to load two PLA filaments of clearly different"
              " colors (for example orange and white).\n\nIf the filaments"
              " are already loaded, tap Print."), image)

    flows = {
        'bed_assist': [
            remove_glass, heat, clean,
            _step(LIVE, _("Calibrate Left Point"),
                  _("Turn the left leveling wheel under the bed until the"
                    " orange bar reaches the middle. If no orange bar is"
                    " shown, keep turning as indicated."),
                  'pic_leveling_bed_calibration_auxiliary_left_point_content',
                  enter="SNAPMAKER_CAL_DATUM POINT=1", point=2, tool=0),
            _step(LIVE, _("Calibrate Right Point"),
                  _("Turn the right leveling wheel under the bed until the"
                    " orange bar reaches the middle. If no orange bar is"
                    " shown, keep turning as indicated."),
                  'pic_leveling_bed_calibration_auxiliary_right_point_content',
                  point=3, tool=0),
            restore_glass, success],
        'bed_manual': [
            _step(CHECK, _("Prepare Bed Leveling"),
                  _("1. Remove the glass plate and put it in a safe place.\n"
                    "2. Turn both wheels at the front underneath the bed"
                    " clockwise until they stop.\n"
                    "3. Make sure the nozzle tips are clean."),
                  'gif_leveling_bed_auxiliary_calibration_info',
                  enter="SNAPMAKER_CAL_BEGIN",
                  leave="SNAPMAKER_CAL_MOVE POINT=1 TOOL=0 Z=5"),
            _step(INFO, _("Calibrate Datum Point"),
                  _("Place the calibration card between the left nozzle and"
                    " the heated bed and tap Next. Then lower the nozzle"
                    " until you feel slight resistance when pulling the card"
                    " and it wrinkles when you push it.")),
            _step(JOG, _("Calibrate Datum Point"),
                  _("Adjust the height until the calibration card has slight"
                    " resistance."),
                  leave="SNAPMAKER_CAL_MOVE POINT=2 TOOL=0 KEEP_Z=1"),
            _step(INFO, _("Calibrate Left Point"),
                  _("Turn the front left wheel under the heated bed until the"
                    " calibration card has the same resistance at this"
                    " point."),
                  leave="SNAPMAKER_CAL_MOVE POINT=3 TOOL=0 KEEP_Z=1"),
            _step(INFO, _("Calibrate Right Point"),
                  _("Turn the front right wheel under the heated bed until"
                    " the calibration card has the same resistance at this"
                    " point."),
                  leave="SNAPMAKER_CAL_END SAVE=0"),
            success],
        'z_assist': [
            dict(remove_glass), loosen_screws, heat, clean,
            _step(LIVE, _("Calibrate Z Offset"),
                  _("Turn the thumbwheel of the right extruder until the"
                    " orange bar reaches the middle. If no orange bar is"
                    " shown, keep turning as indicated."),
                  'pic_leveling_z_calibration_auxiliary_content',
                  enter="SNAPMAKER_CAL_DATUM POINT=3 ORIGIN=0", point=3,
                  tool=1,
                  invert=True),
            restore_z, success],
        'z_manual': [
            _step(CHECK, _("Prepare Z Offset Calibration"),
                  _("Both nozzles are brought to the bed one after the"
                    " other and set to the same working height with the"
                    " calibration card.\n\nRemove the glass plate and make"
                    " sure both nozzle tips are clean."),
                  'gif_leveling_bed_auxiliary_calibration_info',
                  enter="SNAPMAKER_CAL_BEGIN",
                  leave="SNAPMAKER_CAL_MOVE POINT=1 TOOL=0 Z=5"),
            _step(INFO, _("Calibrate Z Offset - Toolhead L"),
                  _("Place the calibration card between the nozzle and the"
                    " heated bed and tap Next. Then lower the nozzle until"
                    " you feel slight resistance when pulling the card and"
                    " it wrinkles when you push it.")),
            _step(JOG, _("Calibrate Z Offset - Toolhead L"),
                  _("Adjust the height until the calibration card has slight"
                    " resistance."),
                  leave="SNAPMAKER_CAL_SET_ORIGIN\n"
                        "SNAPMAKER_CAL_MOVE POINT=1 TOOL=1 KEEP_Z=1"),
            _step(INFO, _("Calibrate Z Offset - Toolhead R"),
                  _("Turn the thumbwheel of the right toolhead until the"
                    " calibration card has the same resistance."),
                  leave="SNAPMAKER_CAL_END SAVE=1"),
            success],
        'xy_assist': [
            dict(remove_glass), heat, clean,
            _step(RUN, _("Calibrate XY Offset"),
                  _("The machine is measuring and calibrating"
                    " automatically..."),
                  'gif_leveling_xy_calibration_content',
                  enter="SNAPMAKER_CAL_XY",
                  done_text=_("The X and Y offsets of the two extruders have"
                              " been calibrated.")),
            restore_glass, success],
        'xy_manual': [
            _step(CHECK, _("Prepare XY Offset Calibration"),
                  _("A test model is printed with both extruders. You then"
                    " pick the best matching line group of the X and Y test"
                    " patterns to correct the offset of the right"
                    " extruder.\n\nInstall the glass plate and load"
                    " filament into both extruders."),
                  'ic_j1_calibration'),
            _step(PRINT, _("Print Calibration Model"), "",
                  'gif_j1_calibration_print_calibration_model',
                  file='snapmaker_xy_offset_test.gcode'),
            _step(OFFSET, _("Correct XY Offset"),
                  _("Enter how far the lines of the right extruder are"
                    " shifted against the lines of the left extruder"
                    " (positive: to the right/back)."), 'ic_j1_calibration'),
            success],
        'check': [
            install_glass, load('pic_calibration_j1_z_offset_load_filament'),
            _step(PRINT, _("Print Check Model"), "",
                  'gif_j1_calibration_check_printing',
                  file='snapmaker_calibration_check.gcode'),
            _step(INFO, _("Check Z Offset Calibration"),
                  _("If the surfaces of the differently colored areas are"
                    " flush with each other, the Z offset calibration is"
                    " good. If not, repeat the calibration.\n\nTap Next to"
                    " check the XY offset calibration."),
                  'pic_j1_calibration_check_for_z_offset'),
            _step(INFO, _("Check XY Offset Calibration"),
                  _("Take the model off the PEI glass plate and try to break"
                    " off the four outer squares. If all four can be broken"
                    " off (not necessarily completely), the XY offset"
                    " calibration is good. If not, repeat the calibration."),
                  'pic_j1_calibration_check_for_xy_offset', last=True)],
        'vibration': [
            install_glass,
            load('pic_calibration_j1_z_offset_load_filament_for_vibration'),
            _step(PRINT, _("Print Calibration Model"), "",
                  'gif_j1_calibration_print_calibration_model',
                  file='snapmaker_vibration_test.gcode'),
            _step(INFO, _("Choose the Best Area"),
                  _("1. Look at the marked areas on the X and Y sides of the"
                    " model.\n2. On each side, find the area with the least"
                    " visible vertical ripples.\n3. Tap Next to select them."),
                  'pic_j1_calibration_vibration'),
            _step(CHOICE, _("Choose for Y Model"),
                  _("If two areas look equally good and better than the"
                    " others, choose either."),
                  'pic_j1_calibration_vibration_model', axis='Y'),
            _step(CHOICE, _("Choose for X Model"),
                  _("If two areas look equally good and better than the"
                    " others, choose either."),
                  'pic_j1_calibration_vibration_model', axis='X'),
            success],
    }
    for heater, temp in PID_HEATERS:
        flows['pid_' + heater] = [
            _step(INFO, _("PID Auto Tune - %s") % pid_heater_name(heater),
                  _("The heater is heated to %d°C and switched on and off"
                    " several times to measure it; its PID values are"
                    " calculated from that. This takes about 5 to 15"
                    " minutes.\n\nKeep the printer closed and the part fans"
                    " off, and do not touch the heater.") % temp
                  + (_(" The nozzles first move off their parking wipers.")
                     if heater != 'heater_bed' else ""),
                  'gif_calibration_j1_z_offset_heat_noaales_and_bed'),
            _step(PID, _("PID Auto Tune - %s") % pid_heater_name(heater),
                  _("The heater is being tuned..."),
                  'gif_calibration_j1_z_offset_heat_noaales_and_bed',
                  enter="PID_CALIBRATE HEATER=%s TARGET=%d" % (heater, temp),
                  heater=heater),
            success]
    menu = [
        {'key': 'bed', 'title': _("Heated Bed Leveling"), 'assist': True,
         'flows': ('bed_assist', 'bed_manual'),
         'images': ('gif_calibration_j1_heated_bed_leveing_auxiliary_content',
                    'ic_j1_calibration'),
         'texts': (_("The left extruder touches the heated bed at three"
                     " points in sequence. To level the bed, adjust the"
                     " height at two of these points as instructed."),
                   _("The left extruder is moved to three points of the"
                     " heated bed in sequence. Level the bed with the"
                     " calibration card as instructed."))},
        {'key': 'z', 'title': _("Z Offset Calibration"), 'assist': True,
         'flows': ('z_assist', 'z_manual'),
         'images': ('gif_calibration_j1_z_offset_calibration_content',
                    'ic_j1_calibration'),
         'texts': (_("Both extruders touch the heated bed in sequence; you"
                     " adjust the right extruder so that both work at the"
                     " same height."),
                   _("Both extruders are moved to the heated bed in"
                     " sequence; you set both to the same height with the"
                     " calibration card."))},
        {'key': 'xy', 'title': _("XY Offset Calibration"), 'assist': True,
         'flows': ('xy_assist', 'xy_manual'),
         'images': (
             'gif_calibration_j1_xy_offset_auxiliary_calibration_content',
                    'ic_j1_calibration'),
         'texts': (_("Both extruders touch the calibration feature of the"
                     " heated bed in sequence to measure and calibrate"
                     " their X and Y offsets automatically."),
                   _("Print the X and Y calibration model and pick the best"
                     " line groups to calibrate the X and Y offsets of the"
                     " two extruders."))},
        {'key': 'check', 'title': _("Offset Calibration Check"),
         'assist': False, 'flows': ('check',),
         'images': ('pic_model_check_360x408',),
         'texts': (_("A built-in model is printed with both extruders. Check"
                     " it as shown on the screen to see whether the offset"
                     " calibrations are good."),)},
        {'key': 'vibration', 'title': _("Vibration Compensation"),
         'assist': False, 'flows': ('vibration',),
         'images': ('pic_calibration_j1_clibration_vibration_content',),
         'texts': (_("To improve the print quality with vibration"
                     " compensation, calibrate the compensation frequency"
                     " following the instructions on the screen."),)},
        # The entries below the line are optional
        {'key': 'pid', 'title': _("PID Auto Tune"), 'assist': False,
         'separator': True,
         'setting': 'pid', 'flows': (),
         'images': ('gif_calibration_j1_z_offset_heat_noaales_and_bed',),
         'texts': (_("Tunes the temperature control of a heater, the"
                     " nozzles at 235°C, the bed at 60°C. New values apply"
                     " at once."),)},
        {'key': 'plate', 'title': _("Build Plate"), 'assist': False,
         'setting': 'plate_thickness', 'flows': (),
         'images': ('gif_calibration_j1_xy_offset_restore_machine',),
         'texts': (_("Thickness of the build plate on the heated bed"
                     " (5.0 mm for the PEI glass plate of the J1). The"
                     " calibrations measure the bare bed; the nozzles"
                     " start printing this much higher.\n\nSet it when"
                     " you use another build plate."),)},
    ]
    return menu, flows
