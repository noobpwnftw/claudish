"""Probe: read the focused Terminal.app through the accessibility API (needs the Accessibility permission for
the Python running it, and pyobjc-framework-ApplicationServices). The system-wide focused element fails with
-25204 (cannot complete); asking the frontmost app for its focused element works."""
import subprocess, time
from ApplicationServices import (AXIsProcessTrusted, AXUIElementCreateSystemWide, AXUIElementCopyAttributeValue,
                                 kAXFocusedUIElementAttribute, kAXRoleAttribute, kAXValueAttribute)
print("trusted:", AXIsProcessTrusted())
subprocess.run(["osascript", "-e", 'tell application "Terminal" to activate', "-e",
                'tell application "Terminal" to do script "cd /tmp; gti status; ls /nope"'])
time.sleep(3)
t0 = time.monotonic()
system = AXUIElementCreateSystemWide()
err, focused = AXUIElementCopyAttributeValue(system, kAXFocusedUIElementAttribute, None)
print("system-wide err", err)
from ApplicationServices import AXUIElementCreateApplication
from AppKit import NSWorkspace
front = NSWorkspace.sharedWorkspace().frontmostApplication()
print("frontmost", front.localizedName(), front.bundleIdentifier())
t0 = time.monotonic()
err, focused = AXUIElementCopyAttributeValue(AXUIElementCreateApplication(front.processIdentifier()), kAXFocusedUIElementAttribute, None)
print("focused err", err)
if focused is not None:
    _, role = AXUIElementCopyAttributeValue(focused, kAXRoleAttribute, None)
    _, value = AXUIElementCopyAttributeValue(focused, kAXValueAttribute, None)
    from ApplicationServices import AXUIElementGetPid
    _, pid = AXUIElementGetPid(focused, None)
    app = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True).stdout.strip()
    print("role", role, "app", app, "ms %.1f" % ((time.monotonic() - t0) * 1000), "chars", len(value or ""))
    print("---\n" + "\n".join((value or "").rstrip().splitlines()[-6:]) + "\n---")
subprocess.run(["osascript", "-e", 'tell application "Terminal" to quit'])
