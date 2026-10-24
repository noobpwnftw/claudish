"""cd_AI's settings window on macOS (G62): `Claudish settings`, from the input menu's "Settings…"
and once at the end of install. A native window around the page the service serves
(claudish/web/settings.html), so every platform shows the same settings; this file is only the
window: its menus (Edit, so a key can be pasted), one window at a time, and closing it quits.
"""
import os
import sys
import time

from AppKit import (NSAlert, NSApplication, NSApplicationActivationPolicyRegular, NSBackingStoreBuffered,
                    NSImage, NSMenu, NSMenuItem, NSRunningApplication, NSWindow, NSWindowStyleMaskClosable,
                    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable, NSWindowStyleMaskTitled)
from Foundation import NSData, NSObject, NSURL, NSURLRequest
from WebKit import WKWebView, WKWebViewConfiguration

LOCK = os.path.join(os.path.expanduser("~/Library/Caches"), "cd_AI-settings.pid")


class Closer(NSObject):
    def windowWillClose_(self, notification):
        try:
            os.remove(LOCK)
        except OSError:
            pass
        NSApplication.sharedApplication().terminate_(None)  # exits here


def menus(app):
    """The app menu (Close, Quit) and Edit (cut, copy, paste, select all): a web view takes ⌘V
    only through a menu item."""
    bar = NSMenu.alloc().init()
    for title, items in (("cd_AI", [("Close", "performClose:", "w"), ("Quit cd_AI Settings", "terminate:", "q")]),
                         ("Edit", [("Undo", "undo:", "z"), ("Redo", "redo:", "Z"), None, ("Cut", "cut:", "x"),
                                   ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")])):
        menu = NSMenu.alloc().initWithTitle_(title)
        for item in items:
            menu.addItem_(NSMenuItem.separatorItem() if item is None else
                          NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(*item))
        holder = NSMenuItem.alloc().init()
        holder.setSubmenu_(menu)
        bar.addItem_(holder)
    app.setMainMenu_(bar)


def already_open():
    """True when a settings window is open already (it is brought forward instead)."""
    try:
        pid = int(open(LOCK).read())
    except (OSError, ValueError):
        return False
    running = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if running is None or running.isTerminated():
        return False
    running.activateWithOptions_(0)
    return True


def show():
    from claudish.client import settings_url
    if already_open():
        return 0
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)  # a Dock icon and menus while it is open
    from importlib.resources import files
    picture = files("claudish").joinpath("web", "favicon.png").read_bytes()  # cd_AI's icon, as on the page
    icon = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(picture, len(picture)))
    if icon is not None:
        app.setApplicationIconImage_(icon)
    menus(app)
    for attempt in range(20):  # just installed, the service may still be starting
        try:
            url = settings_url()
            break
        except OSError:
            time.sleep(0.5)
    else:
        alert = NSAlert.alloc().init()
        alert.setMessageText_("cd_AI's service is not running")
        alert.setInformativeText_("It starts at login. To start it now, run this in Terminal:\n"
                                  "launchctl kickstart gui/%d/com.claudish.service" % os.getuid())
        app.activateIgnoringOtherApps_(True)
        alert.runModal()
        return 1
    with open(LOCK, "w") as out:
        out.write(str(os.getpid()))
    style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
             | NSWindowStyleMaskResizable)
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (560, 720)), style,
                                                                          NSBackingStoreBuffered, False)
    window.setTitle_("cd_AI Settings")
    window.setContentMinSize_((420, 360))
    view = WKWebView.alloc().initWithFrame_configuration_(((0, 0), (560, 720)), WKWebViewConfiguration.alloc().init())
    window.setContentView_(view)
    view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))
    closer = Closer.alloc().init()
    window.setDelegate_(closer)
    window.setReleasedWhenClosed_(False)
    window.center()
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(show())
