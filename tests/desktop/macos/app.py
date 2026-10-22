"""A plain Cocoa window with a text view that mirrors its text (and marked text) to a JSON file,
like tests/desktop/linux/app.py: the macOS typing test reads it without Apple Events, which would
need an Automation permission that nobody can grant on a CI machine."""
import json
import os
import sys

from AppKit import (NSApp, NSApplication, NSApplicationActivationPolicyRegular, NSBackingStoreBuffered,
                    NSMakeRect, NSTextView, NSWindow, NSWindowStyleMaskTitled)
from Foundation import NSObject, NSTimer

STATE, COMMANDS = sys.argv[1], sys.argv[2]


class Mirror(NSObject):
    def tick_(self, timer):
        try:
            with open(COMMANDS) as source:
                command = source.read().strip()
            if command:
                open(COMMANDS, "w").close()
                if command == "clear":
                    view.setString_("")
                NSApp.activateIgnoringOtherApps_(True)
                window.makeKeyAndOrderFront_(None)
                window.makeFirstResponder_(view)
        except OSError:
            pass
        marked = ""
        if view.hasMarkedText():
            location, length = view.markedRange()
            marked = str(view.string())[location:location + length]
        with open(STATE + ".tmp", "w") as out:
            json.dump({"text": str(view.string()), "marked": marked, "active": bool(NSApp.isActive())}, out)
        os.replace(STATE + ".tmp", STATE)


app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    NSMakeRect(200, 200, 600, 300), NSWindowStyleMaskTitled, NSBackingStoreBuffered, False)
window.setTitle_("Claudish test app")
view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 600, 300))
view.setAutomaticDashSubstitutionEnabled_(False)  # the app's own substitutions are not the input method's
view.setAutomaticQuoteSubstitutionEnabled_(False)
window.setContentView_(view)
window.makeKeyAndOrderFront_(None)
window.makeFirstResponder_(view)
app.activateIgnoringOtherApps_(True)
mirror = Mirror.alloc().init()
NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.05, mirror, "tick:", None, True)
app.run()
