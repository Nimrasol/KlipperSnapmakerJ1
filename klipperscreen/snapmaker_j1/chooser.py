# Touch friendly choice for drop-down lists of KlipperScreen
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# GTK opens a drop-down list over its current entry, so long lists run
# off the screen and their last entries cannot be reached by touch.  A tap
# on the drop-down opens a dialog with all entries as buttons instead;
# choosing one sets the drop-down as the list would.
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

COLUMNS = 3


def attach(screen, combo, title):
    gesture = Gtk.GestureMultiPress.new(combo)
    gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

    def pressed(gesture, *args):
        # The list of GTK does not open
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def released(gesture, *args):
        if combo.get_sensitive():
            _show(screen, combo, title)

    gesture.connect("pressed", pressed)
    gesture.connect("released", released)
    # Kept with the drop-down
    combo.snapmaker_chooser = gesture


def _show(screen, combo, title):
    gtk = screen.gtk
    grid = Gtk.Grid(column_homogeneous=True, row_spacing=5, column_spacing=5,
                    vexpand=True, valign=Gtk.Align.CENTER)
    label = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
    label.set_markup("<big><b>%s</b></big>" % title)
    grid.attach(label, 0, 0, COLUMNS, 1)
    dialog = None
    active = combo.get_active_id()

    def chosen(button, value):
        gtk.remove_dialog(dialog)
        if value != combo.get_active_id():
            combo.set_active_id(value)

    for i, row in enumerate(combo.get_model()):
        text, value = row[0], row[1]
        button = gtk.Button(None, text, None, scale=.66)
        button.set_vexpand(False)
        if value == active:
            button.get_style_context().add_class("dialog-primary")
        button.connect("clicked", chosen, value)
        grid.attach(button, i % COLUMNS, 1 + i // COLUMNS, 1, 1)
    scroll = gtk.ScrolledWindow()
    scroll.add(grid)
    dialog = gtk.Dialog(title, [{"name": _("Cancel"),
                                 "response": Gtk.ResponseType.CANCEL}],
                        scroll, lambda d, response: gtk.remove_dialog(d))
