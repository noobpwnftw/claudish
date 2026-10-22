"""A plain GTK window: entry, text view, password entry. Mirrors their contents to a JSON file."""
import json
import os
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

STATE, COMMANDS = sys.argv[1], sys.argv[2]
window = Gtk.Window(title="Claudish test app")
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
entry, other, password = Gtk.Entry(), Gtk.Entry(), Gtk.Entry()
password.set_visibility(False)
password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
view = Gtk.TextView()
view.set_size_request(600, 200)
widgets = {"entry": entry, "other": other, "password": password, "view": view}
for widget in widgets.values():
    box.pack_start(widget, False, False, 0)
window.add(box)
window.connect("destroy", Gtk.main_quit)
window.show_all()


def text(widget):
    if isinstance(widget, Gtk.TextView):
        buffer = widget.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
    return widget.get_text()


def tick():
    # The driver asks for focus changes through a file, so no window manager is needed.
    try:
        with open(COMMANDS) as source:
            name = source.read().strip()
        if name in widgets:
            window.present()
            widgets[name].grab_focus()
            open(COMMANDS, "w").close()
    except OSError:
        pass
    focused = next((name for name, widget in widgets.items() if widget.has_focus()), None)
    with open(STATE + ".tmp", "w") as out:
        json.dump({"focus": focused, **{name: text(widget) for name, widget in widgets.items()}}, out)
    os.replace(STATE + ".tmp", STATE)
    return True


GLib.timeout_add(50, tick)
Gtk.main()
