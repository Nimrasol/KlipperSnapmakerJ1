# Tests of klipperscreen/snapmaker_j1/style.py (colors of the touch screen):
# python -m unittest discover tests
import importlib.util
import os
import sys
import types
import unittest

# The module loads GTK, which the color helpers do not use
_gi = types.ModuleType("gi")
_gi.require_version = lambda *args: None
_repo = types.ModuleType("gi.repository")
_repo.Gdk = _repo.Gtk = None
sys.modules.setdefault("gi", _gi)
sys.modules.setdefault("gi.repository", _repo)
_spec = importlib.util.spec_from_file_location(
    "snapmaker_j1_style",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                 "klipperscreen", "snapmaker_j1", "style.py"))
style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(style)


class TempColor(unittest.TestCase):
    def test_colors(self):
        color = style.temp_color
        self.assertEqual(color(25., 0., 5), style.TITLE)        # off
        self.assertEqual(color(150., 220., 5), style.ERROR)     # heating
        self.assertEqual(color(215., 220., 5), style.SUCCESS)   # 5 below
        self.assertEqual(color(225., 220., 5), style.SUCCESS)   # 5 above
        self.assertEqual(color(225.1, 220., 5), style.COOLING)  # cooling

    def test_rgb(self):
        self.assertEqual(style.rgb("#ff0080"), (1., 0., 128 / 255.))


if __name__ == "__main__":
    unittest.main()
