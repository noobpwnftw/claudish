"""cd_AI's settings window on macOS (G62): `Claudish settings`, from the input menu's "Settings…"
and once at the end of a first install (`--first`). A native window around the page the service
serves (claudish/web/settings.html), so every platform shows the same settings; this file is only
the window: its menus (Edit, so a key can be pasted), one window at a time, links in the browser,
and closing it quits.
"""
import fcntl
import os
import sys
import time

import objc
from AppKit import (NSAlert, NSApplication, NSApplicationActivationPolicyRegular, NSBackingStoreBuffered,
                    NSBezierPath, NSColor, NSGraphicsContext, NSImage, NSMenu, NSMenuItem, NSRunningApplication,
                    NSShadow, NSWindow, NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable,
                    NSWindowStyleMaskResizable, NSWindowStyleMaskTitled, NSWorkspace)
from Foundation import NSData, NSObject, NSURL, NSURLRequest
from WebKit import WKNavigationActionPolicyAllow, WKNavigationActionPolicyCancel, WKWebView, WKWebViewConfiguration

LOCK = os.path.join(os.path.expanduser("~/Library/Caches"), "cd_AI-settings.lock")


class Delegate(NSObject):
    def windowWillClose_(self, notification):
        NSApplication.sharedApplication().terminate_(None)

    @objc.signature(b"v@:@@@?")
    def webView_decidePolicyForNavigationAction_decisionHandler_(self, view, action, handler):
        """The settings page stays in the window; a link (Anthropic's console) opens in the browser."""
        url = action.request().URL()
        if url is not None and str(url.host() or "") not in ("127.0.0.1", "localhost"):
            NSWorkspace.sharedWorkspace().openURL_(url)
            handler(WKNavigationActionPolicyCancel)
        else:
            handler(WKNavigationActionPolicyAllow)

    @objc.signature(b"@@:@@@@")
    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(self, view, configuration,
                                                                                   action, features):
        """A link with target=_blank: the browser too."""
        if action.request().URL() is not None:
            NSWorkspace.sharedWorkspace().openURL_(action.request().URL())
        return None


def menus(app):
    """The app menu (Hide, Quit), Edit (a web view takes ⌘V only through a menu item) and Window."""
    bar = NSMenu.alloc().init()
    for title, items in (("cd_AI", [("Hide cd_AI Settings", "hide:", "h"), None, ("Quit cd_AI Settings", "terminate:", "q")]),
                         ("Edit", [("Undo", "undo:", "z"), ("Redo", "redo:", "Z"), None, ("Cut", "cut:", "x"),
                                   ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")]),
                         ("Window", [("Close", "performClose:", "w"), ("Minimize", "performMiniaturize:", "m")])):
        menu = NSMenu.alloc().initWithTitle_(title)
        for item in items:
            menu.addItem_(NSMenuItem.separatorItem() if item is None else
                          NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(*item))
        holder = NSMenuItem.alloc().init()
        holder.setSubmenu_(menu)
        bar.addItem_(holder)
        if title == "Window":
            app.setWindowsMenu_(menu)
    app.setMainMenu_(bar)


def dock_icon(artwork):
    """The artwork on Apple's icon grid, as every other Dock icon: a rounded square 824 of 1024
    points wide, centred, with a soft shadow below."""
    icon = NSImage.alloc().initWithSize_((1024, 1024))
    icon.lockFocus()
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_((0, -10))
    shadow.setShadowBlurRadius_(24)
    shadow.setShadowColor_(NSColor.colorWithWhite_alpha_(0, 0.3))
    shape = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(((100, 100), (824, 824)), 185, 185)
    NSGraphicsContext.saveGraphicsState()
    shadow.set()
    NSColor.whiteColor().setFill()
    shape.fill()
    NSGraphicsContext.restoreGraphicsState()
    shape.addClip()
    artwork.drawInRect_(((100, 100), (824, 824)))
    icon.unlockFocus()
    return icon


def single():
    """The lock for the one settings window, held while this process lives (the system drops it
    when it ends, however it ends), or None when another window holds it: that one comes forward."""
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    held = open(LOCK, "a+")
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        held.seek(0)
        try:
            other = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(held.read() or 0))
            if other is not None:
                other.activateWithOptions_(0)
        except ValueError:
            pass
        held.close()
        return None
    held.seek(0)
    held.truncate()
    held.write(str(os.getpid()))
    held.flush()
    return held


def show(first=False):
    from importlib.resources import files
    from claudish.client import settings_url
    lock = single()
    if lock is None:
        return 0
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)  # a Dock icon and menus while it is open
    picture = files("claudish").joinpath("web", "favicon.png").read_bytes()  # cd_AI's icon, as on the page
    artwork = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(picture, len(picture)))
    if artwork is not None:
        app.setApplicationIconImage_(dock_icon(artwork))
    menus(app)
    for attempt in range(20):  # just installed, the service may still be starting
        try:
            url = settings_url() + ("&first=1" if first else "")
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
    style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
             | NSWindowStyleMaskResizable)
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (560, 720)), style,
                                                                          NSBackingStoreBuffered, False)
    window.setTitle_("cd_AI Settings")
    window.setContentMinSize_((420, 360))
    view = WKWebView.alloc().initWithFrame_configuration_(((0, 0), (560, 720)), WKWebViewConfiguration.alloc().init())
    delegate = Delegate.alloc().init()
    view.setNavigationDelegate_(delegate)
    view.setUIDelegate_(delegate)
    window.setContentView_(view)
    view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))
    window.setDelegate_(delegate)
    window.setReleasedWhenClosed_(False)
    window.center()
    window.setFrameAutosaveName_("cd_AI Settings")  # where you left it, next time
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(show("--first" in sys.argv))
