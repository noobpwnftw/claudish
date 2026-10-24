"""Entry point bundled as Claudish.app by py2app.

Started by macOS, it is the input method. With arguments it is the rest of cd_AI, so one bundle
with its own Python is all an install needs (G61): `Claudish serve|init|key|setup|doctor|...` run
the claudish command line, and `Claudish register` adds and enables the input source.
"""
import os
import sys

# py2app points SSL_CERT_FILE at a certificate file the bundle does not carry; without it, the HTTP
# client uses the system's trust store (truststore), which is what a Mac should use.
if os.environ.get("SSL_CERT_FILE") and not os.path.exists(os.environ["SSL_CERT_FILE"]):
    del os.environ["SSL_CERT_FILE"]

from AppKit import NSApplication
from Foundation import NSBundle
from InputMethodKit import IMKServer
from PyObjCTools import AppHelper
from controller import ClaudishInputController  # Registers the Objective-C controller class.


def command_line():
    """The bundle run with arguments: True when it handled them."""
    if len(sys.argv) < 2:
        return False
    if sys.argv[1] == "register":
        import sources
        bundle = NSBundle.mainBundle()
        identifier = str(bundle.bundleIdentifier())
        print("register:", sources.register(str(bundle.bundlePath()), identifier))
        print("enable:", sources.enable(identifier))  # macOS asks once: "Allow … to enable cd_AI?"
        # Not selected: which input source is in use stays the person's choice (Control-Space).
        return True
    from claudish.__main__ import main as claudish
    sys.argv = ["claudish"] + sys.argv[1:]
    claudish()
    return True


def main():
    if command_line():
        return
    NSApplication.sharedApplication()
    bundle = NSBundle.mainBundle()
    server = IMKServer.alloc().initWithName_bundleIdentifier_(
        bundle.objectForInfoDictionaryKey_("InputMethodConnectionName"), bundle.bundleIdentifier())
    if server is None:
        raise RuntimeError("InputMethodKit could not create the input-method server")
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
