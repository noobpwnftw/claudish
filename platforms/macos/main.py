"""Entry point bundled as Claudish.app by py2app."""
from AppKit import NSApplication
from Foundation import NSBundle
from InputMethodKit import IMKServer
from PyObjCTools import AppHelper
from controller import ClaudishInputController  # Registers the Objective-C controller class.


def main():
    NSApplication.sharedApplication()
    bundle = NSBundle.mainBundle()
    server = IMKServer.alloc().initWithName_bundleIdentifier_(
        bundle.objectForInfoDictionaryKey_("InputMethodConnectionName"), bundle.bundleIdentifier())
    if server is None:
        raise RuntimeError("InputMethodKit could not create the input-method server")
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
