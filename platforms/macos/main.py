"""Entry point bundled as Claudish.app by py2app.

Started by macOS, it is the input method. With arguments it is the rest of cd_AI, so one bundle
with its own Python is all an install needs (G61): `Claudish serve|init|key|setup|doctor|...` run
the claudish command line, and `Claudish register` adds and enables the input source.
"""
import os
import sys

# py2app points SSL_CERT_FILE at a certificate file the bundle does not carry, and the bundle's
# OpenSSL has no certificates of its own (python.org's Python leaves that to "Install
# Certificates"): HTTPS (Anthropic's API) fails "certificate verify failed". The bundle carries
# certifi's as a file.
if not os.path.exists(os.environ.get("SSL_CERT_FILE") or ""):
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
# The certificates are this process's, not the programs it starts (claude, codex, uvx): theirs are
# the system's (the Keychain), which may hold a company proxy's certificate that certifi lacks.
from claudish.children import OWN_ENV  # noqa: E402
OWN_ENV.add("SSL_CERT_FILE")

# py2app's launcher also sets PYTHONHOME and PYTHONPATH to the bundle and SSL_CERT_DIR to a folder
# that does not exist. This Python has started; the programs cd_AI runs (MCP servers, context
# commands, agents) get the environment without them: another Python would load the bundle's
# packages and fail, and OpenSSL would look for certificates in the missing folder. cd_AI starts
# itself through the launcher (EXECUTABLEPATH), which sets them again.
os.environ.pop("PYTHONHOME", None)
os.environ.pop("PYTHONPATH", None)
if not os.path.isdir(os.environ.get("SSL_CERT_DIR") or ""):
    os.environ.pop("SSL_CERT_DIR", None)

# AppKit, InputMethodKit and the controller load in main(), for the input method only: the service
# (`Claudish serve`, started at login) and the other commands do not wait on them (seconds at login).


def command_line():
    """The bundle run with arguments: True when it handled them."""
    if len(sys.argv) < 2:
        return False
    if sys.argv[1] == "register":
        import sources
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        identifier = str(bundle.bundleIdentifier())
        from controller import MODE_IDS
        print("register:", sources.register(str(bundle.bundlePath()), identifier, MODE_IDS.values()))
        print("enable:", sources.enable(identifier))  # macOS asks once: "Allow … to enable cd_AI?"
        # Not selected: which input source is in use stays the person's choice (Control-Space).
        return True
    from claudish.__main__ import main as claudish
    sys.argv = ["claudish"] + sys.argv[1:]
    claudish()
    return True


def from_terminal():
    """A command's end as a command line's: an exception is its traceback on stderr and exit status
    1, never py2app's "Launch error" window (which it shows for any uncaught exception, even for a
    command typed in a terminal: `Claudish doctor | head` closing the pipe opened one)."""
    try:
        handled = command_line()
    except SystemExit:
        raise
    except BrokenPipeError:  # the reader went (head): as any command line does, end quietly
        stdout_gone()
        sys.exit(1)
    except BaseException:  # noqa: BLE001 - every end is the terminal's, Ctrl+C included
        import traceback
        traceback.print_exc()
        sys.exit(1)
    try:
        sys.stdout.flush()  # here, where a closed pipe is caught, not at exit
    except BrokenPipeError:
        stdout_gone()
    return handled


def stdout_gone():
    """The reader of stdout went: what is left goes nowhere, so nothing fails to flush at exit."""
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def main():
    if from_terminal():
        return
    from AppKit import NSApplication
    from Foundation import NSBundle
    from InputMethodKit import IMKServer
    from PyObjCTools import AppHelper
    from controller import ClaudishInputController  # noqa: F401 (registers the Objective-C controller class)
    NSApplication.sharedApplication()
    bundle = NSBundle.mainBundle()
    server = IMKServer.alloc().initWithName_bundleIdentifier_(
        bundle.objectForInfoDictionaryKey_("InputMethodConnectionName"), bundle.bundleIdentifier())
    if server is None:
        raise RuntimeError("InputMethodKit could not create the input-method server")
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
