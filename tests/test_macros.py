# Tests of macros in config/snapmaker-j1-macros.cfg, rendered with Jinja2
# as Klipper does: python -m unittest discover tests
import os
import unittest

try:
    import jinja2
except ImportError:
    jinja2 = None

MACROS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                      "config", "snapmaker-j1-macros.cfg")


def macro_gcode(name):
    # The indented gcode: lines of the [gcode_macro <name>] section
    lines, inside, gcode = [], False, False
    with open(MACROS, encoding="utf-8") as f:
        for line in f:
            if line.startswith("["):
                if inside:
                    break
                inside = line.strip() == "[gcode_macro %s]" % (name,)
            elif inside and line.startswith("gcode:"):
                gcode = True
            elif inside and gcode and line.startswith((" ", "\n")):
                lines.append(line.strip())
    return "\n".join(lines)


def render(name, params, printer):
    # Klipper's delimiters: {% %} and { }
    env = jinja2.Environment("{%", "%}", "{", "}")
    out = env.from_string(macro_gcode(name)).render(params=params,
                                                     printer=printer)
    return [line for line in out.splitlines() if line.strip()]


@unittest.skipUnless(jinja2, "Jinja2 not installed")
class CalTemp(unittest.TestCase):
    def cal_temp(self, delta, bed, **params):
        printer = {"gcode_macro SNAPMAKER_CAL_MATERIAL":
                   {"nozzle_delta": delta, "bed": bed}}
        return render("_SNAPMAKER_CAL_TEMP", params, printer)

    def test_pla_keeps_the_file_values(self):
        self.assertEqual(self.cal_temp(0, 0, CMD="M109", T="1", S="210"),
                         ["M109 T1 S210.0"])
        self.assertEqual(self.cal_temp(0, 0, CMD="M140", S="65"),
                         ["M140 S65.0"])

    def test_petg_raises_nozzles_and_sets_the_bed(self):
        self.assertEqual(self.cal_temp(30, 75, CMD="m104", S="210"),
                         ["M104 S240.0"])
        self.assertEqual(self.cal_temp(30, 75, CMD="M190", S="65"),
                         ["M190 S75"])

    def test_off_stays_off(self):
        self.assertEqual(self.cal_temp(40, 90, CMD="M104", T="0", S="0"),
                         ["M104 T0 S0.0"])
        self.assertEqual(self.cal_temp(40, 90, CMD="M140", S="0"),
                         ["M140 S0.0"])


if __name__ == "__main__":
    unittest.main()
