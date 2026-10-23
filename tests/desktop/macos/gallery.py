"""Screenshots of every state cd_AI shows on macOS, for the visual pass (G45).

Runs on the Mac (over SSH, in the rig's venv), typing into the rig's test app with the rig's own
helpers. Each state is announced in /tmp/claudish-gallery-state; the host (gallery.sh) captures the
screen over VNC and answers in /tmp/claudish-gallery-ack. Nothing is checked: the pictures are the
output. Needs cd_AI installed and selected, and the service running.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import driver  # noqa: E402  the rig: the test app, post/type_text/key/shift_tap, front()

STATE, ACK = Path("/tmp/claudish-gallery-state"), Path("/tmp/claudish-gallery-ack")


def show(name):
    ACK.unlink(missing_ok=True)
    STATE.write_text(name)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not ACK.exists():
        time.sleep(0.1)


def main():
    import subprocess
    driver.COMMANDS.write_text("")
    app = subprocess.Popen([sys.executable, str(driver.HERE / "app.py"), str(driver.STATE), str(driver.COMMANDS)])
    try:
        driver.wait_for(lambda: driver.state().get("active"), timeout=20)
        driver.fresh_document()
        driver.select_input_method()
        driver.front()
        driver.type_text("Thanks for the review ")
        time.sleep(2.5)  # the suggestion is cd_AI's own overlay, not marked text: give it time
        show("01-continue-suggestion")
        driver.key("Escape")
        driver.fresh_document()
        driver.shift_tap()  # compose
        driver.type_text("this is very important")
        time.sleep(0.5)
        show("02-compose-typing")
        driver.key("Tab")  # the rewrite in place
        time.sleep(1.2)
        show("03-rewrite-in-place")
        driver.key("Escape")
        driver.key("Escape")
        driver.fresh_document()
        driver.type_text("say hi")
        driver.key("Return")  # an instruction's drafts
        time.sleep(1.5)
        show("04-instruct-drafts")
        driver.key("Return")  # Enter on a draft: nothing inserted, the row's Tab lit
        time.sleep(0.4)
        show("04b-enter-on-drafts")
        driver.key("Escape")
        driver.key("Escape")
        driver.fresh_document()
        # A long instruction: the panel opens at its end; when Enter sends it, it moves to the caret.
        driver.type_text("write a short note to the whole team thanking them for shipping on time")
        time.sleep(1.0)
        show("05-long-instruction")
        driver.key("Return")
        time.sleep(1.5)
        show("06-long-instruction-sent")
        driver.key("Escape")
        driver.key("Escape")
    finally:
        STATE.write_text("done")
        app.terminate()


if __name__ == "__main__":
    main()
