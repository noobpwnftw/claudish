"""A plain Cocoa window with a text view that mirrors its text (and marked text) to a JSON file,
like tests/desktop/linux/app.py: the macOS typing test reads it without Apple Events, which would
need an Automation permission that nobody can grant on a CI machine."""
import json
import os
import sys

from AppKit import (NSApp, NSFont, NSScrollView, NSForegroundColorAttributeName, NSApplication, NSApplicationActivationPolicyRegular, NSBackingStoreBuffered,
                    NSMakeRect, NSSecureTextField, NSTextView, NSView, NSWindow, NSWindowStyleMaskTitled)
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
                    other.setString_("")
                    secret.setStringValue_("")
                NSApp.activateIgnoringOtherApps_(True)
                window.makeKeyAndOrderFront_(None)
                window.makeFirstResponder_({"other": other, "secret": secret}.get(command, view))
        except OSError:
            pass
        marked, color = "", ""
        if view.hasMarkedText():
            location, length = view.markedRange()
            marked = str(view.string())[location:location + length]
            if length:  # how it is drawn: continue's suggestion should not look like typed text
                found = view.textStorage().attribute_atIndex_effectiveRange_(NSForegroundColorAttributeName,
                                                                            location, None)[0]
                color = str(found.colorNameComponent()) if found is not None and found.type() == 2 else str(found)
        with open(STATE + ".tmp", "w") as out:
            json.dump({"text": str(view.string()), "other": str(other.string()), "secret": str(secret.stringValue()), "marked": marked, "marked_color": color, "active": bool(NSApp.isActive())}, out)
        os.replace(STATE + ".tmp", STATE)


app = NSApplication.sharedApplication()
app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    NSMakeRect(200, 200, 600, 300), NSWindowStyleMaskTitled, NSBackingStoreBuffered, False)
window.setTitle_("Claudish test app")
content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 600, 300))
# The main field in a scroll view, as text views are in real apps (TextEdit, Mail, Notes): IMK reports
# the caret's rectangle the way those apps do (a bare text view reports it a line too high).
scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 100, 600, 200))
view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 600, 200))
view.setFont_(NSFont.systemFontOfSize_(14))
scroll.setDocumentView_(view)
scroll.setHasVerticalScroller_(True)
other = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 600, 60))  # a second field, for focus changes
secret = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(10, 66, 580, 24))  # a password field
for field in (view, other):
    field.setAutomaticDashSubstitutionEnabled_(False)  # the app's own substitutions are not the input method's
    field.setAutomaticQuoteSubstitutionEnabled_(False)
content.addSubview_(scroll)
content.addSubview_(other)
content.addSubview_(secret)
window.setContentView_(content)
window.makeKeyAndOrderFront_(None)
window.makeFirstResponder_(view)
app.activateIgnoringOtherApps_(True)
mirror = Mirror.alloc().init()
NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.05, mirror, "tick:", None, True)
app.run()
