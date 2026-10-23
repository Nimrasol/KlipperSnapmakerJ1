# Snapmaker J1 calibration menu for KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

from . import flows as F
from . import style as S

IMAGE_DIRS = ["~/printer_data/config/snapmaker_j1/images",
              os.path.join(os.path.dirname(__file__), "images")]
IMAGE_EXTS = ("gif", "png", "webp")
# Height indicator of the stock display (HorizontalPrecisionIndicator):
# the bar moves by the indicator width per millimetre, so it is visible
# within about +/-0.54mm; further out a chevron points to the bar
INDICATOR_LIMIT = 2.5
INDICATOR_VALID = 0.08
INDICATOR_VISUAL = 1.
JOG_STEPS = [-1., -.1, -.05, .05, .1, 1.]
OFFSET_STEP = .05
# Build plate thickness setting (mm), as SNAPMAKER_SET_PLATE_THICKNESS
PLATE_DEFAULT = 5.
PLATE_MAX = 10.
PLATE_STEP = .1


def _rgb(color):
    rgba = Gdk.RGBA()
    rgba.parse(color)
    return rgba.red, rgba.green, rgba.blue


def _find_image(name):
    for d in IMAGE_DIRS:
        for ext in IMAGE_EXTS:
            path = os.path.join(os.path.expanduser(d), "%s.%s" % (name, ext))
            if os.path.exists(path):
                return path
    return None


def _icon(name, size):
    path = _find_image(name)
    if path is None:
        logging.info("Calibration picture %s not found", name)
        return None
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
    except GLib.Error:
        logging.exception("Unable to load %s", path)
        return None


class HeightIndicator(Gtk.Box):
    """Height difference bar with the direction to turn the wheel."""

    # Stock pictures; the text marks are used when they are missing
    STATUS = {"valid": ("icon_tips_success_64x64", "✓"),
              "clockwise": ("icon_calibration_clockwise", "↻"),
              "anticlockwise": ("icon_calibration_anti_clockwise",
                                "↺")}

    def __init__(self, dp):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,
                         spacing=int(12 * dp), hexpand=True)
        self.dp = dp
        self.value = None
        self.icons = {key: _icon(name, int(32 * dp))
                      for key, (name, mark) in self.STATUS.items()}
        size = int(24 * dp)
        self.chevrons = [_icon("pic_slide_indicator_left", size),
                         _icon("pic_slide_indicator_right", size)]
        self.status = Gtk.Image()
        self.status.set_size_request(-1, int(32 * dp))
        self.mark = Gtk.Label()
        self.mark.get_style_context().add_class("snap-value")
        status = Gtk.Box(halign=Gtk.Align.CENTER)
        status.pack_start(self.status, False, False, 0)
        status.pack_start(self.mark, False, False, 0)
        self.pack_start(status, False, False, 0)
        self.bar = Gtk.DrawingArea(hexpand=True)
        self.bar.set_size_request(-1, int(24 * dp))
        self.bar.connect("draw", self._draw)
        self.pack_start(self.bar, False, False, 0)

    def set_value(self, value):
        self.value = max(-INDICATOR_LIMIT, min(INDICATOR_LIMIT, value))
        if abs(self.value) < .5 * INDICATOR_VALID:
            key = "valid"
        elif self.value < -.5 * INDICATOR_VALID:
            key = "clockwise"
        else:
            key = "anticlockwise"
        if self.icons[key] is not None:
            self.status.set_from_pixbuf(self.icons[key])
            self.mark.set_label("")
        else:
            self.status.clear()
            self.mark.set_label(self.STATUS[key][1])
        self.bar.queue_draw()

    def _draw(self, widget, cr):
        import cairo
        dp = self.dp
        w = widget.get_allocated_width()
        mid, y = w / 2., widget.get_allocated_height() / 2.
        stroke = 5 * dp
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(stroke)
        # Track fading out to both ends
        r, g, b = _rgb(S.CARD_TOP)
        track = cairo.LinearGradient(0, 0, w, 0)
        track.add_color_stop_rgba(0., r, g, b, .2)
        track.add_color_stop_rgba(.5, r, g, b, 1.)
        track.add_color_stop_rgba(1., r, g, b, .2)
        cr.set_source(track)
        cr.move_to(10 * dp, y)
        cr.line_to(w - 10 * dp, y)
        cr.stroke()
        cr.set_source_rgb(*_rgb(S.EXPLAIN))
        cr.set_line_width(1.5 * dp)
        cr.move_to(mid, y - 11 * dp)
        cr.line_to(mid, y + 11 * dp)
        cr.stroke()
        if self.value is None:
            return
        v = self.value
        cr.set_source_rgb(*_rgb(S.PRIMARY))
        cr.set_line_width(stroke)
        left = mid + w * (v - .5 * INDICATOR_VALID)
        cr.move_to(left, y)
        cr.line_to(left + w * INDICATOR_VALID, y)
        cr.stroke()
        if abs(v) <= .5 * (INDICATOR_VISUAL + INDICATOR_VALID):
            return
        # Bar out of view: one chevron, two when far out
        side = 1 if v > 0 else 0
        x = w - 14 * dp if side else 14 * dp
        far = abs(v) >= INDICATOR_LIMIT - 1.
        for offset in ((-5 * dp, 5 * dp) if far else (0,)):
            self._chevron(cr, side, x + offset, y)

    def _chevron(self, cr, side, x, y):
        pixbuf = self.chevrons[side]
        if pixbuf is not None:
            Gdk.cairo_set_source_pixbuf(
                cr, pixbuf, x - pixbuf.get_width() / 2.,
                y - pixbuf.get_height() / 2.)
            cr.paint()
            return
        d = 6 * self.dp * (1 if side else -1)
        cr.set_source_rgb(*_rgb(S.PRIMARY))
        cr.set_line_width(2.5 * self.dp)
        cr.move_to(x - d / 2., y - abs(d))
        cr.line_to(x + d / 2., y)
        cr.line_to(x - d / 2., y + abs(d))
        cr.stroke()


class AnimatedImage(Gtk.Image):
    """Animation scaled to the size of the stock layout."""

    def __init__(self, animation, width, height):
        super().__init__()
        ratio = min(width / animation.get_width(),
                    height / animation.get_height())
        self.size = (max(1, int(animation.get_width() * ratio)),
                     max(1, int(animation.get_height() * ratio)))
        self.iter = animation.get_iter(None)
        self.timer = None
        self._show_frame()
        self.connect("map", lambda w: self._schedule())
        self.connect("unmap", lambda w: self._stop())

    def _show_frame(self):
        self.set_from_pixbuf(self.iter.get_pixbuf().scale_simple(
            self.size[0], self.size[1], GdkPixbuf.InterpType.BILINEAR))

    def _schedule(self):
        delay = self.iter.get_delay_time()
        if delay >= 0 and self.timer is None:
            self.timer = GLib.timeout_add(max(delay, 20), self._tick)

    def _stop(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def _tick(self):
        self.timer = None
        self.iter.advance(None)
        self._show_frame()
        self._schedule()
        return False


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Calibration")
        super().__init__(screen, title)
        S.install(screen)
        self.menu_items, self.flows = F.build()
        self.assist = {item["key"]: True for item in self.menu_items}
        self.selected = 0
        self.flow = None
        self.index = 0
        self.step_widgets = {}
        self.pending = False
        self.live_running = False
        self.choice = None
        self.offset = [0., 0.]
        self.step_ready = False
        self.plate_thickness = self.plate_value = PLATE_DEFAULT
        self.menu_box = self._build_menu()
        self.content.add(self.menu_box)
        self._select(None, 0)

    # Helpers
    def _dp(self, value):
        return int(round(S.dp(self._screen, value)))

    def _image(self, name, width, height):
        path = _find_image(name)
        try:
            if path is not None and path.endswith(".gif"):
                anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
                if not anim.is_static_image():
                    return AnimatedImage(anim, width, height)
                pixbuf = anim.get_static_image()
            elif path is not None:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            if path is not None:
                ratio = min(width / pixbuf.get_width(),
                            height / pixbuf.get_height())
                pixbuf = pixbuf.scale_simple(
                    int(pixbuf.get_width() * ratio),
                    int(pixbuf.get_height() * ratio),
                    GdkPixbuf.InterpType.BILINEAR)
                return Gtk.Image.new_from_pixbuf(pixbuf)
            logging.info("Calibration picture %s not found", name)
        except GLib.Error:
            logging.exception("Unable to load %s", path)
        label = Gtk.Label(label="")
        label.set_size_request(width, height)
        return label

    @staticmethod
    def _label(text, style=None, **kwargs):
        # A bounded width makes long texts wrap instead of widening the page
        label = Gtk.Label(label=text, wrap=True, xalign=0, yalign=0,
                          wrap_mode=Pango.WrapMode.WORD_CHAR,
                          width_chars=20, max_width_chars=40, **kwargs)
        if style:
            label.get_style_context().add_class(style)
        return label

    def _body_label(self, text, **kwargs):
        # Body text of the stock pages: 16sp with 6dp extra line spacing
        label = self._label(text, **kwargs)
        if hasattr(Pango, "attr_line_height_new"):  # Pango 1.50 and newer
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_line_height_new(1.35))
            label.set_attributes(attrs)
        return label

    @staticmethod
    def _styled(widget, *classes):
        ctx = widget.get_style_context()
        for name in classes:
            ctx.add_class(name)
        return widget

    def _button(self, label, kind, small=False):
        button = Gtk.Button(label=label, can_focus=False,
                            valign=Gtk.Align.CENTER)
        self._styled(button, "snap-" + kind)
        if small:
            self._styled(button, "snap-small")
        return button

    def _root(self, child):
        root = Gtk.EventBox(hexpand=True, vexpand=True)
        self._styled(root, "snapj1")
        root.add(child)
        return root

    def _bottom_bar(self):
        # 60dp bar at the bottom of the stock pages
        bar = Gtk.Box(spacing=self._dp(12), hexpand=True)
        self._styled(bar, "snap-card")
        bar.set_size_request(-1, self._dp(60))
        return bar

    def _bar_button(self, button, side):
        # Buttons keep 12dp to the ends of the bottom bar
        getattr(button, "set_margin_" + side)(self._dp(12))
        return button

    def _clear(self):
        for child in self.content.get_children():
            self.content.remove(child)

    def _gcode(self, script, callback=None):
        logging.info("Calibration: %s", script.replace("\n", "; "))
        self.pending = True

        def done(result, method, params, *args):
            self.pending = False
            self._set_ready(self.step_ready)
            if "error" in result:
                message = result["error"].get("message", str(result["error"]))
                self._error(message)
                return
            if callback is not None:
                callback()

        self._screen._ws.api.gcode_script(script, done)

    def _stat(self, obj, field, default=None):
        value = self._printer.get_stat(obj, field)
        return default if value in ({}, None) else value

    # Menu: section list on the left, detail card on the right
    def _build_menu(self):
        box = Gtk.Box(hexpand=True, vexpand=True)
        # hexpand=False keeps the expanding labels from widening the list
        sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                           hexpand=False)
        sections.set_size_request(self._dp(140), -1)
        sections.set_margin_top(self._dp(4))
        self.section_buttons = []
        for i, item in enumerate(self.menu_items):
            row = Gtk.Box(spacing=self._dp(6), hexpand=True,
                          halign=Gtk.Align.FILL)
            label = Gtk.Label(label=item["title"], wrap=True, xalign=0,
                              hexpand=True, max_width_chars=12,
                              wrap_mode=Pango.WrapMode.WORD_CHAR)
            row.pack_start(label, True, True, 0)
            indicator = self._styled(Gtk.Box(valign=Gtk.Align.CENTER),
                                     "snap-indicator")
            row.pack_start(indicator, False, False, 0)
            button = Gtk.Button(can_focus=False, halign=Gtk.Align.START)
            button.add(row)
            button.set_size_request(self._dp(128), self._dp(56))
            self._styled(button, "snap-section")
            button.connect("clicked", self._select, i)
            sections.pack_start(button, False, False, 0)
            self.section_buttons.append(button)
        box.pack_start(sections, False, False, 0)
        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                              hexpand=True, vexpand=True)
        self._styled(self.detail, "snap-card")
        self.detail.set_margin_top(self._dp(8))
        self.detail.set_margin_end(self._dp(16))
        self.detail.set_margin_bottom(self._dp(16))
        box.pack_start(self.detail, True, True, 0)
        return self._root(box)

    def _select(self, widget, index):
        self.selected = index
        for i, button in enumerate(self.section_buttons):
            ctx = button.get_style_context()
            if i == index:
                ctx.add_class("selected")
            else:
                ctx.remove_class("selected")
        self._show_detail()

    def _flow_index(self, item):
        return 0 if (not item["assist"] or self.assist[item["key"]]) else 1

    def _show_detail(self):
        for child in self.detail.get_children():
            self.detail.remove(child)
        item = self.menu_items[self.selected]
        i = self._flow_index(item)
        row = Gtk.Box(spacing=self._dp(16), vexpand=True)
        image = self._image(item["images"][i], self._dp(180), self._dp(204))
        image.set_valign(Gtk.Align.START)
        image.set_margin_top(self._dp(16))
        image.set_margin_start(self._dp(16))
        row.pack_start(image, False, False, 0)
        text = self._body_label(item["texts"][i], hexpand=True)
        text.set_margin_top(self._dp(20))
        text.set_margin_end(self._dp(16))
        row.pack_start(text, True, True, 0)
        self.detail.pack_start(row, True, True, 0)
        bottom = self._bottom_bar()
        if item.get("setting") == "plate_thickness":
            self._plate_controls(text, bottom)
            self.detail.pack_start(bottom, False, False, 0)
            self.detail.show_all()
            return
        if item["assist"]:
            switch = Gtk.Switch(active=self.assist[item["key"]],
                                valign=Gtk.Align.CENTER, can_focus=False)
            switch.set_margin_start(self._dp(12))
            switch.connect("notify::active", self._assist_changed, item)
            bottom.pack_start(switch, False, False, 0)
            bottom.pack_start(self._styled(Gtk.Label(label=_("Assist Mode")),
                                           "snap-assist"), False, False, 0)
        start = self._bar_button(self._button(_("Start"), "primary"), "end")
        start.connect("clicked", self._start)
        bottom.pack_end(start, False, False, 0)
        self.detail.pack_start(bottom, False, False, 0)
        self.detail.show_all()

    # Build plate thickness: a setting, no workflow
    def _plate_controls(self, text, bottom):
        minus = self._button("-%.1f" % PLATE_STEP, "secondary", small=True)
        plus = self._button("+%.1f" % PLATE_STEP, "secondary", small=True)
        value = self._styled(Gtk.Label(width_chars=7), "snap-value")
        minus.connect("clicked", self._change_plate, -PLATE_STEP, value)
        plus.connect("clicked", self._change_plate, PLATE_STEP, value)
        bottom.pack_start(self._bar_button(minus, "start"), False, False, 0)
        bottom.pack_start(value, False, False, 0)
        bottom.pack_start(plus, False, False, 0)
        save = self._bar_button(self._button(_("Save"), "primary"), "end")
        save.connect("clicked", self._save_plate)
        bottom.pack_end(save, False, False, 0)
        self.plate_widgets = (value, save)
        self._update_plate()

    def _change_plate(self, widget, delta, label):
        self.plate_value = round(
            min(max(self.plate_value + delta, 0.), PLATE_MAX), 2)
        self._update_plate()

    def _update_plate(self):
        value, save = self.plate_widgets
        value.set_label("%.1f mm" % (self.plate_value,))
        save.set_sensitive(abs(self.plate_value - self.plate_thickness)
                           > .001)

    def _save_plate(self, widget):
        # Klipper restarts to apply the moved Z origin
        self._gcode("SNAPMAKER_SET_PLATE_THICKNESS THICKNESS=%.2f"
                    % (self.plate_value,),
                    lambda: self._screen._ws.api.gcode_script("SAVE_CONFIG"))

    def _assist_changed(self, switch, param, item):
        self.assist[item["key"]] = switch.get_active()
        self._gcode("SAVE_VARIABLE VARIABLE=snap_j1_assist_%s VALUE=%s"
                    % (item["key"], switch.get_active()))
        self._show_detail()

    def activate(self):
        # Restore the assist mode choices stored in Klipper and the build
        # plate thickness in use
        def got(result, method, params, *args):
            try:
                status = result["result"]["status"]
                svv = status["save_variables"]["variables"]
            except (KeyError, TypeError):
                return
            thickness = status.get("probe", {}).get("plate_thickness")
            if thickness is not None:
                self.plate_thickness = self.plate_value = thickness
            for key in self.assist:
                self.assist[key] = bool(svv.get("snap_j1_assist_%s" % key,
                                                True))
            if self.flow is None:
                self._show_detail()

        self._screen._ws.api.query_objects(
            {"save_variables": ["variables"], "probe": ["plate_thickness"]},
            got)

    # Workflow
    def _start(self, widget):
        item = self.menu_items[self.selected]
        self.flow = self.flows[item["flows"][self._flow_index(item)]]
        self.index = 0
        self._show_step()

    def _show_step(self):
        step = self.flow[self.index]
        self._clear()
        self.step_ready = False
        self.step_widgets = {}
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True,
                       vexpand=True)
        self._styled(card, "snap-card", "snap-page-card")
        card.set_margin_top(self._dp(8))
        for side in ("start", "end", "bottom"):
            getattr(card, "set_margin_" + side)(self._dp(16))
        if step["kind"] == F.SUCCESS:
            card.pack_start(self._success_body(step), True, True, 0)
        else:
            card.pack_start(self._step_body(step), True, True, 0)
        buttons = self._bottom_bar()
        if step["kind"] != F.SUCCESS:
            quit_button = self._bar_button(
                self._button(_("Quit"), "secondary"), "start")
            quit_button.connect("clicked", self._ask_quit)
            buttons.pack_start(quit_button, False, False, 0)
        for extra in self.step_widgets.get("extra_buttons", []):
            buttons.pack_start(extra, False, False, 0)
        label = _("Complete") if (step["kind"] == F.SUCCESS
                                  or step.get("last")) else _("Next")
        next_button = self._bar_button(self._button(label, "primary"),
                                       "end")
        next_button.connect("clicked", self._next)
        next_button.set_sensitive(False)
        self.step_widgets["next"] = next_button
        buttons.pack_end(next_button, False, False, 0)
        card.pack_start(buttons, False, False, 0)
        self.content.add(self._root(card))
        self.content.show_all()
        self._update_live_status()
        if step.get("enter"):
            self._gcode(step["enter"], self._entered)
        else:
            self._entered()

    def _success_body(self, step):
        # Stock fragment_calibration_success: thumbs up and title centered
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                       spacing=self._dp(16), vexpand=True)
        image = self._image(step["image"], self._dp(80), self._dp(80))
        image.set_halign(Gtk.Align.CENTER)
        image.set_margin_top(self._dp(55))
        body.pack_start(image, False, False, 0)
        title = self._styled(Gtk.Label(label=step["title"], wrap=True,
                                       justify=Gtk.Justification.CENTER),
                             "snap-title")
        body.pack_start(title, False, False, 0)
        return body

    def _step_body(self, step):
        body = Gtk.Box(spacing=self._dp(16), vexpand=True)
        body.set_margin_top(self._dp(16))
        body.set_margin_start(self._dp(16))
        body.set_margin_end(self._dp(16))
        if step.get("image"):
            image = self._image(step["image"], self._dp(188), self._dp(204))
            image.set_valign(Gtk.Align.START)
            body.pack_start(image, False, False, 0)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                        spacing=self._dp(12), hexpand=True)
        header = Gtk.Box(spacing=self._dp(12))
        header.pack_start(self._label(step["title"], "snap-title",
                                      hexpand=True), True, True, 0)
        total = len(self.flow) - (self.flow[-1]["kind"] == F.SUCCESS)
        header.pack_end(self._styled(Gtk.Label(
            label="%d/%d" % (self.index + 1, total), yalign=0),
            "snap-progress"), False, False, 0)
        right.pack_start(header, False, False, 0)
        text = self._body_label(step["text"], hexpand=True)
        self.step_widgets["text"] = text
        right.pack_start(text, False, False, 0)
        if step.get("glass_warning"):
            warning = self._label("", "snap-warning")
            self.step_widgets["warning"] = warning
            right.pack_start(warning, False, False, 0)
        getattr(self, "_build_" + step["kind"])(step, right)
        body.pack_start(right, True, True, 0)
        return body

    def _entered(self):
        step = self.flow[self.index]
        kind = step["kind"]
        if kind == F.LIVE:
            self.live_running = True
            self._live_measure()
        elif kind == F.PRINT:
            self._screen.snapmaker_calibration_print = True
            # The stock calibration prints skip the nozzle diameter check
            self._gcode("SDCARD_PRINT_FILE FILENAME=\"%s/%s\" NOZZLE_CHECK=0"
                        % (F.GCODE_DIR, step["file"]))
        elif kind == F.RUN:
            if step.get("done_text"):
                self.step_widgets["text"].set_label(step["done_text"])
            self._set_ready(True)
        elif kind not in (F.HEAT, F.CHECK, F.CHOICE):
            self._set_ready(True)

    def _set_ready(self, ready):
        self.step_ready = ready
        if "next" in self.step_widgets:
            self.step_widgets["next"].set_sensitive(ready and not self.pending)

    def _next(self, widget):
        step = self.flow[self.index]
        if step["kind"] == F.SUCCESS:
            self._finish()
            return
        if step["kind"] == F.LIVE:
            self.live_running = False
            if self.pending:
                # Continue once the running measurement has finished
                self.step_widgets["next"].set_sensitive(False)
                GLib.timeout_add(200, self._wait_live_done)
                return
        script = step.get("leave")
        if step["kind"] == F.CHOICE:
            script = ("SNAPMAKER_SET_VIBRATION_FREQ AXIS=%s FREQ=%d"
                      % (step["axis"], F.VIBRATION_FREQS[self.choice]))
        elif step["kind"] == F.OFFSET:
            script = ("SNAPMAKER_CAL_START\n"
                      "SNAPMAKER_CAL_NOZZLE_OFFSET"
                      " X_ADJUST=%.3f Y_ADJUST=%.3f\n"
                      "SNAPMAKER_CAL_FINISH SAVE=1" % tuple(self.offset))
        elif step["kind"] == F.PRINT:
            self._screen.snapmaker_calibration_print = False
        if step.get("last"):
            script = "SNAPMAKER_CAL_END SAVE=0"
        self.step_widgets["next"].set_sensitive(False)
        if script:
            self._gcode(script, self._advance)
        else:
            self._advance()

    def _wait_live_done(self):
        if self.pending:
            return True
        self._next(None)
        return False

    def _advance(self):
        step = self.flow[self.index]
        if step.get("last"):
            self._back_to_menu()
            return
        self.index += 1
        self._show_step()

    def _finish(self):
        def got(result, method, params, *args):
            try:
                pending = result["result"]["status"]["configfile"][
                    "save_config_pending"]
            except (KeyError, TypeError):
                pending = False
            self._back_to_menu()
            if pending:
                # Klipper restarts to apply the new calibration
                self._screen._ws.api.gcode_script("SAVE_CONFIG")

        self._screen._ws.api.query_objects(
            {"configfile": ["save_config_pending"]}, got)

    def _back_to_menu(self):
        self.flow = None
        self.live_running = False
        self._screen.snapmaker_calibration_print = False
        self._clear()
        self.content.add(self.menu_box)
        self._show_detail()
        self.content.show_all()

    def _ask_quit(self, widget):
        buttons = [
            {"name": _("Quit"), "response": Gtk.ResponseType.OK,
             "style": "dialog-error"},
            {"name": _("Cancel"), "response": Gtk.ResponseType.CANCEL,
             "style": "dialog-info"},
        ]
        label = self._label(_("The current data will not be saved."
                              " Are you sure to quit?"))
        label.set_halign(Gtk.Align.CENTER)
        label.set_valign(Gtk.Align.CENTER)
        self._gtk.Dialog(_("Calibration"), buttons, label, self._quit_response)

    def _quit_response(self, dialog, response_id):
        self._gtk.remove_dialog(dialog)
        if response_id != Gtk.ResponseType.OK:
            return
        self._quit()

    def _quit(self):
        self.live_running = False
        script = "SNAPMAKER_CAL_END SAVE=0"
        if self.flow[self.index]["kind"] == F.PRINT:
            script = "CANCEL_PRINT\n" + script
        self._back_to_menu()
        self._screen._ws.api.gcode_script(script)

    def _error(self, message):
        logging.error("Calibration step failed: %s", message)
        buttons = [{"name": _("OK"), "response": Gtk.ResponseType.OK,
                    "style": "dialog-info"}]
        label = self._label(
            _("The machine failed to obtain the data. You can clean the"
              " nozzle and retry.") + "\n\n" + message)
        if self.flow is not None:
            self._quit()
        self._gtk.Dialog(_("Calibration"), buttons, label,
                         lambda d, r: self._gtk.remove_dialog(d))

    def back(self):
        if self.flow is not None:
            self._ask_quit(None)
            return True
        return False

    # Step builders
    def _build_info(self, step, box):
        pass

    def _build_run(self, step, box):
        pass

    def _build_check(self, step, box):
        check = Gtk.CheckButton(label=_("I have completed the steps above"),
                                can_focus=False)
        check.connect("toggled", lambda w: self._set_ready(w.get_active()))
        box.pack_start(check, False, False, 0)

    def _build_heat(self, step, box):
        grid = Gtk.Grid(column_spacing=self._dp(16),
                        row_spacing=self._dp(6))
        for row, (name, label) in enumerate([
                ("extruder", _("Left nozzle")),
                ("extruder1", _("Right nozzle")),
                ("heater_bed", _("Heated bed"))]):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            value = self._styled(Gtk.Label(label="-", xalign=0), "snap-value")
            self.step_widgets["temp_" + name] = value
            grid.attach(value, 1, row, 1, 1)
        box.pack_start(grid, False, False, 0)

    def _build_live(self, step, box):
        indicator = HeightIndicator(S.dp(self._screen, 1.))
        self.step_widgets["indicator"] = indicator
        box.pack_start(indicator, False, False, 0)
        value = self._styled(Gtk.Label(label=""), "snap-progress")
        self.step_widgets["live_value"] = value
        box.pack_start(value, False, False, 0)

    def _build_jog(self, step, box):
        grid = Gtk.Grid(column_homogeneous=True, column_spacing=self._dp(8))
        for i, distance in enumerate(JOG_STEPS):
            button = self._button("%+g" % distance, "secondary", small=True)
            button.connect("clicked", self._jog, distance)
            grid.attach(button, i, 0, 1, 1)
        box.pack_start(grid, False, False, 0)
        position = self._styled(Gtk.Label(label="", xalign=0), "snap-value")
        self.step_widgets["z"] = position
        box.pack_start(position, False, False, 0)

    def _jog(self, widget, distance):
        if not self.pending:
            self._gcode("SNAPMAKER_CAL_JOG DISTANCE=%.3f" % (distance,))

    def _build_print(self, step, box):
        progress = Gtk.ProgressBar(show_text=True)
        self.step_widgets["progress"] = progress
        box.pack_start(progress, False, False, 0)
        pause = self._button(_("Pause"), "secondary")
        pause.connect("clicked", self._toggle_pause)
        self.step_widgets["pause"] = pause
        self.step_widgets["extra_buttons"] = [pause]

    def _toggle_pause(self, widget):
        state = self._stat("print_stats", "state")
        self._gcode("RESUME" if state == "paused" else "PAUSE")

    def _build_load(self, step, box):
        load = self._button(_("Go to Load"), "secondary")
        load.connect("clicked",
                     lambda w: self._screen.show_panel("extrude"))
        self.step_widgets["extra_buttons"] = [load]

    def _build_choice(self, step, box):
        # GTK always activates one radio button of a group; an unshown
        # group leader makes the user pick an area explicitly
        self.choice = None
        group = Gtk.RadioButton()
        self.step_widgets["radio_group"] = group
        names = [_("Area 1 (top)"), _("Area 2"), _("Area 3"),
                 _("Area 4 (bottom)")]
        for i in range(len(F.VIBRATION_FREQS)):
            radio = Gtk.RadioButton.new_with_label_from_widget(
                group, names[i])
            radio.set_can_focus(False)
            radio.connect("toggled", self._choose, i)
            box.pack_start(radio, False, False, 0)
        self._set_ready(False)

    def _choose(self, widget, index):
        if widget.get_active():
            self.choice = index
            self._set_ready(True)

    def _build_offset(self, step, box):
        self.offset = [0., 0.]
        grid = Gtk.Grid(column_spacing=self._dp(12), row_spacing=self._dp(8))
        for row, axis in enumerate("XY"):
            grid.attach(self._styled(Gtk.Label(label=axis), "snap-value"),
                        0, row, 1, 1)
            minus = self._button("-%.2f" % OFFSET_STEP, "secondary",
                                 small=True)
            plus = self._button("+%.2f" % OFFSET_STEP, "secondary",
                                small=True)
            value = self._styled(Gtk.Label(label="0.00", width_chars=6),
                                 "snap-value")
            minus.connect("clicked", self._change_offset, row, -OFFSET_STEP,
                          value)
            plus.connect("clicked", self._change_offset, row, OFFSET_STEP,
                         value)
            grid.attach(minus, 1, row, 1, 1)
            grid.attach(value, 2, row, 1, 1)
            grid.attach(plus, 3, row, 1, 1)
        box.pack_start(grid, False, False, 0)

    def _change_offset(self, widget, axis, delta, label):
        self.offset[axis] = round(self.offset[axis] + delta, 3)
        label.set_label("%.2f" % (self.offset[axis],))

    # Live measurement
    def _live_measure(self):
        if not self.live_running or self.flow is None:
            return
        step = self.flow[self.index]
        self._gcode("SNAPMAKER_CAL_HEIGHT POINT=%d TOOL=%d SAMPLES=1"
                    % (step["point"], step["tool"]), self._live_result)

    def _live_result(self):
        def got(result, method, params, *args):
            try:
                cal = result["result"]["status"]["probe"]["calibration"]
            except (KeyError, TypeError):
                cal = {}
            step = self.flow[self.index] if self.flow else None
            if step is None or step["kind"] != F.LIVE:
                return
            diff = cal.get("height_difference")
            if diff is not None:
                shown = -diff if step.get("invert") else diff
                self.step_widgets["indicator"].set_value(shown)
                self.step_widgets["live_value"].set_label("%+.3f mm" % shown)
            self._set_ready(bool(cal.get("height_valid")))
            if self.live_running:
                self._live_measure()

        self._screen._ws.api.query_objects({"probe": ["calibration"]}, got)

    # Status updates
    def process_update(self, action, data):
        if action != "notify_status_update" or self.flow is None:
            return
        self._update_live_status()

    def _update_live_status(self):
        step = self.flow[self.index] if self.flow else None
        if step is None:
            return
        bed = self._stat("heater_bed", "temperature", 0.)
        if "warning" in self.step_widgets:
            self.step_widgets["warning"].set_label(
                _("The bed is at %d°C. Wait until it has cooled down below"
                  " 40°C before handling the PEI glass plate.") % bed
                if bed >= 40 else "")
        if step["kind"] == F.HEAT:
            ready = True
            for name in ("extruder", "extruder1", "heater_bed"):
                temp = self._stat(name, "temperature", 0.)
                target = self._stat(name, "target", 0.)
                self.step_widgets["temp_" + name].set_label(
                    "%.0f / %.0f°C" % (temp, target))
                margin = 10 if name == "heater_bed" else 3
                ready = ready and target > 0 and temp >= target - margin
            if ready:
                self.step_widgets["text"].set_label(step["ready_text"])
            self._set_ready(ready)
        elif step["kind"] == F.JOG:
            position = self._stat("toolhead", "position")
            if position:
                self.step_widgets["z"].set_label("Z: %.2f" % position[2])
        elif step["kind"] == F.PRINT:
            progress = self._stat("virtual_sdcard", "progress", 0.)
            self.step_widgets["progress"].set_fraction(progress)
            self.step_widgets["progress"].set_text("%d%%" % (progress * 100))
            state = self._stat("print_stats", "state")
            self.step_widgets["pause"].set_label(
                _("Resume") if state == "paused" else _("Pause"))
            self._set_ready(state == "complete")
