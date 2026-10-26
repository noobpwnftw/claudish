"""A plain Qt window: a line edit. Mirrors their contents to a JSON file, as app.py does for GTK."""
import json
import os
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

STATE, COMMANDS = sys.argv[1], sys.argv[2]
application = QApplication(sys.argv[:1])
preedits = {}


class Line(QLineEdit):
    def inputMethodEvent(self, event):
        preedits["qline"] = event.preeditString()
        super().inputMethodEvent(event)


window = QWidget()
window.setWindowTitle("Claudish Qt test app")
layout = QVBoxLayout(window)
widgets = {"qline": Line()}
for widget in widgets.values():
    layout.addWidget(widget)
window.resize(600, 300)
window.show()


def tick():
    # The driver asks for focus changes (and selections) through a file, so no window manager is needed.
    try:
        with open(COMMANDS) as source:
            command = source.read().split()
        if command and command[0] in widgets:
            widget = widgets[command[0]]
            window.activateWindow()
            widget.setFocus()
            if command[1:] == ["seed-selection"]:
                widget.setText("this is very important")
                widget.setSelection(13, 9)
            open(COMMANDS, "w").close()
    except OSError:
        pass
    focused = next((name for name, widget in widgets.items() if widget.hasFocus()), None)
    with open(STATE + ".tmp", "w") as out:
        json.dump({"focus": focused, "active": window.isActiveWindow(), "preedit": preedits.get(focused, ""),
                   **{name: widget.text() for name, widget in widgets.items()}}, out)
    os.replace(STATE + ".tmp", STATE)


timer = QTimer()
timer.timeout.connect(tick)
timer.start(50)
application.exec_()
