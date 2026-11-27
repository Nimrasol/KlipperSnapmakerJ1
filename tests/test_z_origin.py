# Tests of the Z origin of klippy/extras/snapmaker_j1_probe.py (where Z 0
# lies after a calibration): python -m unittest discover tests
import importlib.util
import os
import sys
import types
import unittest

# The module imports Klipper's mcu, probe and tmc; the Z origin uses none
EXTRAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                      "klippy", "extras")
sys.modules.setdefault("mcu", types.ModuleType("mcu"))
_pkg = types.ModuleType("j1extras")
_pkg.__path__ = [EXTRAS]
sys.modules["j1extras"] = _pkg
for name in ("probe", "tmc"):
    sys.modules["j1extras." + name] = types.ModuleType(name)
_spec = importlib.util.spec_from_file_location(
    "j1extras.snapmaker_j1_probe",
    os.path.join(EXTRAS, "snapmaker_j1_probe.py"))
j1probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(j1probe)

ENDSTOP = 205.0


class Rail:
    position_min = -5.
    def __init__(self):
        self.position_endstop = self.position_max = ENDSTOP
    def get_name(self):
        return "stepper_z"
    def get_range(self):
        return self.position_min, self.position_max


class Kin:
    def __init__(self):
        self.rails = [Rail()]
        self.axes_max = (300., 200., ENDSTOP)
    def update_limits(self, axis, limits):
        pass


class Toolhead:
    def __init__(self, z):
        self.pos = [100., 100., z, 0.]
        self.kin = Kin()
    def get_position(self):
        return list(self.pos)
    def set_position(self, pos):
        self.pos = list(pos)
    def wait_moves(self):
        pass
    def get_kinematics(self):
        return self.kin
    def get_status(self, eventtime):
        return {"homed_axes": "xyz", "axis_minimum": [0., 0., -5., 0.],
                "axis_maximum": [300., 200., ENDSTOP, 0.]}


class Printer:
    def __init__(self, toolhead):
        self.objects = {"toolhead": toolhead, "gcode": self}
        self.saved = {}
    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)
    def get_reactor(self):
        return types.SimpleNamespace(monotonic=lambda: 0.)
    def run_script_from_command(self, script):
        words = dict(w.split("=", 1) for w in script.split()[1:])
        value = words["VALUE"]
        self.saved[words["VARIABLE"]] = None if value == "None" else float(
            value)


class Gcmd:
    def respond_info(self, msg):
        pass


def make_probe(nozzle_z, plate=5.):
    p = object.__new__(j1probe.SnapmakerJ1Probe)
    p.printer = Printer(Toolhead(nozzle_z))
    p.cal_active = True
    p.plate_thickness = plate
    p.pending_z = None
    return p


class ZOrigin(unittest.TestCase):
    def test_manual_card_on_bare_bed_adds_plate(self):
        # Nozzle at card height 0.2 above the bare bed, plate 5 mm: the
        # plate surface becomes Z 0 (the card is the working height)
        p = make_probe(0.2)
        p.cmd_SNAPMAKER_CAL_SET_ORIGIN(Gcmd())
        self.assertAlmostEqual(p.pending_z, 5.2)
        p._store_z_origin(Gcmd(), p.pending_z)
        self.assertAlmostEqual(p.printer.saved["snap_j1_z_endstop"],
                               ENDSTOP - 5.2)
        # The homed bed keeps its place: the nozzle is now 5.2 below Z 0
        self.assertAlmostEqual(p.printer.lookup_object("toolhead").pos[2],
                               -5.0)

    def test_saved_z_offset_moves_origin_up(self):
        # A Z offset of +0.05 (nozzle higher) stored as origin: the endstop
        # comes 0.05 closer, so Z 0 is 0.05 higher
        p = make_probe(10.)
        p._store_z_origin(Gcmd(), 0.05)
        self.assertAlmostEqual(p.printer.saved["snap_j1_z_endstop"],
                               ENDSTOP - 0.05)

    def test_z_touch_stops_past_the_expected_bed(self):
        # A nozzle sensor that misses the bed: the touch ends 3 mm below the
        # expected bare bed (plate surface minus 5 mm plate, later the
        # measured reference) instead of pushing on to the session limit
        p = make_probe(10.)
        p.datum = None
        self.assertAlmostEqual(p._limited_target(2, -1, 50.)[2], -8.)
        p.datum = -4.6
        self.assertAlmostEqual(p._limited_target(2, -1, 50.)[2], -7.6)
        # Outside a calibration session the travel range applies
        p.cal_active = False
        self.assertAlmostEqual(p._limited_target(2, -1, 50.)[2], -5.)


class PendingZOffset(unittest.TestCase):
    # A Z offset saved during a print that ended in a shutdown comes back
    # from save_variables after the restart
    def apply(self, gcode_z):
        p = make_probe(10.)
        p.z_saved_offset = 0.
        p.pending_z_restored = True
        adjusts = []
        p.set_gcode_offset = lambda gcmd: adjusts.append(gcmd)
        p.printer.objects["gcode_move"] = types.SimpleNamespace(
            get_status=lambda: {"homing_origin": types.SimpleNamespace(
                z=gcode_z)})
        p.printer.objects["save_variables"] = types.SimpleNamespace(
            allVariables={j1probe.PENDING_Z_VARIABLE: 0.05})
        gcode = types.SimpleNamespace(
            respond_info=lambda msg: None,
            create_gcode_command=lambda *args: args)
        p._apply_z_offset(gcode, 0.05)
        saved = p.printer.saved
        self.assertAlmostEqual(saved["snap_j1_z_endstop"], ENDSTOP - 0.05)
        self.assertIsNone(saved[j1probe.PENDING_Z_VARIABLE])
        self.assertFalse(p.pending_z_restored)
        return adjusts

    def test_without_resume_only_the_origin_moves(self):
        # The Z offset is 0 after the restart: setting it to -0.05 would
        # cancel the stored offset
        self.assertEqual(self.apply(0.), [])

    def test_after_a_resumed_print_the_offset_goes_back(self):
        # The power loss recovery restored the Z offset of the print
        self.assertEqual(len(self.apply(0.05)), 1)


if __name__ == "__main__":
    unittest.main()
