"""PIME/TSF adapter. Shared files are copied here by package.py (platforms/windows)."""
from textService import TextService
import json
import os
import time

from .composition import MAX_COMPOSITION, MODES, Composition, ShiftTap, blank
from .client import Suggestions
from .screen import is_terminal


def keylog(*fields):
    """Opt-in diagnostics: CLAUDISH_KEYLOG=path appends key routing events."""
    import os
    path = os.environ.get("CLAUDISH_KEYLOG")
    if path:
        try:
            with open(path, "a") as log:
                log.write(" ".join(str(field) for field in fields) + "\n")
        except OSError:
            pass


MODE_COMMAND = 100  # the input indicator's click; its menu items follow
SETTINGS_COMMAND = 200  # Settings… in that menu
# TSF input scopes (InputScope.h) by the names the service understands.
INPUT_SCOPES = {1: "url", 4: "email", 5: "email", 7: "name", 28: "digits", 29: "number",
                31: "password", 32: "phone", 33: "phone", 34: "phone", 35: "phone", 36: "phone"}
TIMER_MS = 100  # how often Claudish's PIME calls back while an answer is on its way


def mode_icon(mode):
    """The taskbar's mode icon: continue's cream "cd" tile or compose's "AI", the same in both themes."""
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "mode-%s.ico" % mode)


def mode_label(mode):
    return mode.capitalize()  # "Continue", "Compose", as other input methods' indicator menus read


def mode_tooltip(mode):
    return "cd_AI · %s (tap Shift to switch)" % mode_label(mode)


# Kept across this process's text service instances: switching to another input method (Chewing,
# say) ends cd_AI's composition and closes its instance, and switching back makes a new one. The mode
# you were in, and each window's open exchange with its worker (the conversation, answers on their
# way), are taken up by the next instance in that window.
LAST_MODE = [None]
PARKED = {}  # the foreground window's process id -> (Composition, Suggestions, when)
UNSEEN = object()  # an instance that has not looked for a parked exchange since it was activated


def park(window, state, worker):
    expire()
    PARKED[window] = (state, worker, time.monotonic())


def expire():
    from .composition import HELD_SECONDS
    for window, (_, _, when) in list(PARKED.items()):
        if time.monotonic() - when > HELD_SECONDS:
            del PARKED[window]


def foreground():
    """The foreground window's process id, or None (not on Windows)."""
    try:
        import ctypes
        from ctypes import wintypes
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(ctypes.windll.user32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value or None
    except (AttributeError, OSError):
        return None


# Keys sent with KEYEVENTF_EXTENDEDKEY: PgUp to Down, Insert, Delete, the Windows keys, keypad /.
EXTENDED_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x6F}


MODIFIER_KEYS = (0x10, 0x11, 0x12, 0x5B)  # Shift, Ctrl, Alt, Windows


def held_chord(event):
    """Ctrl, Alt or Win down with Shift: Windows' layout and language switch, not a Shift tap."""
    return any(event.isKeyDown(key) for key in (0x11, 0x12, 0x5B, 0x5C))


def held(event):
    """The modifiers down with this key."""
    return [key for key in MODIFIER_KEYS if event.isKeyDown(key)]


def replay(vk, modifiers=()):
    """Press the key again for the app just after cd_AI commits what was composed, so one press of a
    shortcut or navigation key both commits and acts. A modifier that was down with it and is up by
    now (a quick tap) is pressed with it again. Nothing is composed by then, so cd_AI lets it through."""
    import threading

    def send():
        try:
            import ctypes
            from ctypes import wintypes

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                            ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

            class MOUSEINPUT(ctypes.Structure):  # the union's largest member: INPUT's size follows it
                _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                            ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

            class UNION(ctypes.Union):  # sized for this Python (PIME's backend is a 32-bit Python)
                _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

            class INPUT(ctypes.Structure):
                _anonymous_ = ("u",)
                _fields_ = [("type", wintypes.DWORD), ("u", UNION)]

            user32 = ctypes.windll.user32
            released = [key for key in modifiers if not user32.GetAsyncKeyState(key) & 0x8000]
            steps = ([(key, 0) for key in released] + [(vk, 0), (vk, 0x2)]
                     + [(key, 0x2) for key in reversed(released)])
            inputs = (INPUT * len(steps))()
            for index, (key, up) in enumerate(steps):
                inputs[index].type = 1  # INPUT_KEYBOARD
                inputs[index].ki = KEYBDINPUT(key, 0, (0x1 if key in EXTENDED_KEYS else 0) | up, 0, 0)
            user32.SendInput(len(steps), inputs, ctypes.sizeof(INPUT))
        except (AttributeError, OSError):  # not on Windows
            pass
    threading.Timer(0.03, send).start()  # after this reply: the commit lands first


def focused_app():
    """The foreground window's program name (for bindings), such as "notepad.exe"; None elsewhere."""
    try:
        import ctypes
        import os
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            size, path = wintypes.DWORD(1024), ctypes.create_unicode_buffer(1024)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                return None
            return os.path.basename(path.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError):  # Not on Windows.
        return None


# The design lab's states, for the Windows gallery's preview (test plumbing; see preview()).
PREVIEW = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Claudish", "lab-preview.js")


def open_settings():
    """cd_AI's settings in the browser, the same page on every OS. Asking the service for the page's
    link happens off the input thread: typing never waits on it."""
    import threading
    import webbrowser
    from .client import settings_url

    def open_it():
        try:
            webbrowser.open(settings_url())
        except Exception:
            pass  # no service: nothing to open; doctor says why
    threading.Thread(target=open_it, daemon=True).start()


class ClaudishTextService(TextService):
    def __init__(self, client):
        super().__init__(client)
        self.state = Composition()
        if LAST_MODE[0] and LAST_MODE[0] != self.state.mode:
            self.state.mode = LAST_MODE[0]  # back to cd_AI from another input method: the same mode
        self.shift = ShiftTap()  # Shift alone, tapped: the mode switch
        self.worker = None
        self.adopted_from = UNSEEN

    def onActivate(self):
        keylog("onActivate", id(self), "parked=%s" % list(PARKED))
        if self.worker is None:
            self.worker = Suggestions()
        self.setKeyboardOpen(True)
        # The drafts also go to TSF's candidate list (apps that draw candidates themselves): PIME
        # lists as many as there are selection keys. Choices are not numbered (digits are text), so
        # the keys are blanks: nothing shows a number that selects nothing.
        self.setSelKeys("\u00a0" * 9)
        self.customizeUI(candPerRow=1)
        # The mode in the taskbar's input indicator (PIME's Windows 8+ mode icon); its menu picks one.
        self.addButton("windows-mode-icon", icon=mode_icon(self.state.mode), commandId=MODE_COMMAND,
                       tooltip=mode_tooltip(self.state.mode))

    def switch_mode(self):
        """A Shift tap, or a click or pick on the input indicator: continue <-> compose. Leaving
        compose keeps what you see, as typed."""
        kept = self.state.toggle()
        LAST_MODE[0] = self.state.mode
        if self.worker:
            self.worker.schedule(self.state.revision, "")  # what was asked belongs to the old mode
        self.setCommitString(kept)  # ends the composition; "" inserts nothing
        self.setToast(self.state.toast(), 2)
        self.changeButton("windows-mode-icon", icon=mode_icon(self.state.mode), tooltip=mode_tooltip(self.state.mode))
        self.changed()

    def onCommand(self, commandId, commandType):
        if commandId == MODE_COMMAND:  # a click on the indicator: the other mode, as a Shift tap
            self.switch_mode()
        elif MODE_COMMAND < commandId <= MODE_COMMAND + len(MODES):  # a pick from its menu
            if self.state.mode != MODES[commandId - MODE_COMMAND - 1]:
                self.switch_mode()
        elif commandId == SETTINGS_COMMAND:
            open_settings()

    def onMenu(self, buttonId):
        if buttonId != "windows-mode-icon":
            return None
        return [{"text": mode_label(mode), "id": MODE_COMMAND + 1 + index, "checked": mode == self.state.mode}
                for index, mode in enumerate(MODES)] + [{}, {"text": "Settings…", "id": SETTINGS_COMMAND}]

    def onDeactivate(self):
        """Another input method takes over: an open exchange is held, as on a focus change, and
        parked with its worker for the next cd_AI instance in this app (pause, not stop)."""
        keylog("onDeactivate", id(self), "sent=%s held=%s" % (self.state.sent, self.state.held is not None))
        if self.state.sent:
            self.state.leave(getattr(self, "last_document", None))
        if self.worker:
            park(foreground(), self.state, self.worker)
            self.worker = None
            self.state = Composition()
        self.state.change("")
        self.adopted_from = UNSEEN  # activated again (this instance or a new one): look for it again

    def adopt_parked(self):
        """At the first request after activation: this window's parked exchange and worker, if any."""
        window = foreground()
        if self.adopted_from == window:
            return
        self.adopted_from = window
        expire()
        parked = PARKED.get(window)
        keylog("adopt", id(self), window, "found=%s" % (parked is not None))
        if parked is None or parked[1] is self.worker:
            return
        del PARKED[window]
        state, worker, _ = parked
        if self.worker is not None:
            self.worker.close()
        state.mode = self.state.mode
        self.state, self.worker = state, worker

    def sensitive(self):
        """A password field (IS_PASSWORD): cd_AI stays out, as IBus does for its password purpose."""
        return self.field() == "password"

    def follow_document(self):
        """One conversation per text box: Claudish's PIME names the TSF context of each request."""
        self.adopt_parked()
        document = getattr(self, "document", None)
        if document and document != getattr(self, "last_document", None):
            if getattr(self, "last_document", None) is not None and self.worker:
                self.worker.new_conversation()
            if self.state.sent:  # an instruction's exchange, left in the other text box: held for it
                self.state.leave(self.last_document)
            self.last_document = document
            pill = self.state.returned(document)  # back where one was held: a pill, taking no keys
            if pill:
                self.setToast(pill, 3)

    def preview(self):
        """Screenshot plumbing: with the design lab's
        states at PREVIEW, each F12 draws the next one with the real panel, to compare with the lab.
        Without that file F12 is the app's."""
        if not os.path.exists(PREVIEW):
            return False
        if getattr(self, "previews", None) is None:
            with open(PREVIEW, encoding="utf-8") as source:
                text = source.read()
            self.previews = list(json.loads(text[text.index("{"):text.rindex("}") + 1]).items())
        name, spec = self.previews.pop(0) if self.previews else (None, None)
        if name is None:
            self.previews = None
            self.setPanel(None)
            self.setShowCandidates(False)
            return True
        if name in ("dropped", "returned", "mode-compose", "mode-continue"):  # toasts (scripts/lab_states.py)
            self.setPanel(None)
            self.setShowCandidates(False)
            self.setToast(spec, 30)
        else:
            self.setPanel(spec)
            self.setShowCandidates(True)
        return True

    def filterKeyDown(self, event):
        keylog("filterKeyDown", hex(event.keyCode), "ctrl=%d" % event.isKeyDown(0x11), "len=%d" % len(self.state.text))
        if event.keyCode == 0x7B and os.path.exists(PREVIEW):  # F12, with the lab's states there: the gallery
            return True
        if not self.keyboardOpen or self.sensitive():
            return False
        self.adopt_parked()  # back from another input method: this app's exchange decides what is taken
        if event.keyCode == 0x10:  # Shift: perhaps a tap, the mode switch (seen at its key-up)
            self.shift.press(time.monotonic(), chord=held_chord(event))
            self.switching = False
            return False
        self.shift.other()
        self.switching = False
        self.hideMessage()  # a key ends a toast: it was said where the caret was
        if event.keyCode in (0x11, 0x12, 0x14, 0x5B, 0x5C):
            return False
        # AltGr arrives as Ctrl+Alt; a printable result is typing, not a shortcut.
        if self.shortcut(event):
            if self.state.live:  # nothing is held back in continue mode
                self.drop_live()
                return False
            # Mid-composition, take the key so onKeyDown commits the wording. Left to TSF, the
            # composition was discarded (Ctrl+A lost the typed text).
            return bool(self.state.text)
        if self.state.live:
            self.poll_results()  # a waiting suggestion decides whether Tab is ours
            # Continue types into the app. Tab and Esc are ours only while a suggestion shows;
            # Backspace, Enter, and navigation are the app's (the context follows here).
            if event.keyCode in (0x09, 0x1B):
                return bool(self.state.ghost)
            if event.isPrintableChar():
                return True
            # Backspace, Enter, navigation: the app's. The context starts over from the app's text at
            # the next key (this runs twice per key, in TSF's test and again for the key itself, so
            # it changes nothing that a second run would change again).
            if event.keyCode not in (0x10, 0x14, 0x77):
                self.drop_live()
            return False
        # Shift+Esc with nothing composed: the exchange you left, or the instruction Esc dropped, comes back.
        restoring = event.keyCode == 0x1B and event.isKeyDown(0x10) and bool(self.state.dropped or self.state.held)
        return event.isPrintableChar() or bool(self.state.text) or restoring

    def drop_live(self):
        self.state.change("")
        if self.worker:
            self.worker.schedule(self.state.revision, "")
        self.publish()

    def shortcut(self, event):
        altgr = (event.isKeyDown(0x11) and event.isKeyDown(0x12) and event.isPrintableChar()
                 and not (event.isKeyDown(0x5B) or event.isKeyDown(0x5C)))
        return not altgr and any(event.isKeyDown(key) for key in (0x11, 0x12, 0x5B, 0x5C))

    def publish(self):
        """The screen from the state, in Claudish's PIME (platforms/windows/pime): continue's
        suggestion right after the caret, or the panel Composition.panel() describes (drawn as the
        design lab's Windows 11 mock), and in compose your words as the composition."""
        if self.state.live:
            # Your words are in the app already; the suggestion is cd_AI's own grey text after the
            # caret, and Tab takes it.
            self.setCompositionString("")
            self.setGhost("" if self.state.inside else self.state.ghost)
            self.setPanel(None)
            self.setCandidateList([])
            self.setShowCandidates(False)
            return
        self.setGhost("")
        shown = self.state.shown  # rewrite after Tab: the rewrite, in place of your words
        self.setCompositionString(shown)
        # TSF cursor offsets count UTF-16 code units.
        self.setCompositionCursor(len(shown.encode("utf-16-le")) // 2)
        panel = self.state.panel()
        self.setPanel(panel)
        # The rows also go to TSF's candidate list, for apps that draw candidates themselves.
        self.setCandidateList([row["text"] for row in panel["rows"]] if panel else [])
        self.setShowCandidates(bool(panel))
        self.panel_shown = panel

    def changed(self):
        # Not prose: a URL, an address, a number, or a terminal's command line.
        self.state.quiet = self.field() in ("url", "email", "number", "phone", "digits") or is_terminal(focused_app())
        after = self.around()[1] if self.state.live else ""
        self.state.inside = bool(after.split("\n", 1)[0].strip())  # continue waits for a line's end
        if self.worker and self.state.automatic:
            # Continue asks at once at a word boundary (itself the pause), so the answer is often
            # ready by the time the key is released, and onKeyUp can show it.
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=focused_app(),
                                 immediate=self.state.live, after=after[:500], purpose=self.field())
            self.await_result()
        elif self.worker and not self.state.text:
            self.worker.schedule(self.state.revision, "")
        self.publish()

    def field(self):
        """The field's kind from the input scopes the app declares (Claudish's PIME), as the
        service names them; None for prose or when unknown."""
        if getattr(self, "inputScopes", None) is not None:  # only requests with an edit session carry them
            self.known_scopes = self.inputScopes
        for scope in getattr(self, "known_scopes", None) or ():
            if scope in INPUT_SCOPES:
                return INPUT_SCOPES[scope]
        return None

    def around(self):
        """(before, after): the text around the composition or the caret, as Claudish's PIME
        reports it with key events and timers; empty with a stock PIME."""
        return getattr(self, "textBefore", None) or "", getattr(self, "textAfter", None) or ""

    def await_result(self, seconds=10):
        """Show an answer as soon as it arrives, not at the next key: Claudish's PIME calls back
        (onTimer) in an edit session."""
        self.waiting_until = time.monotonic() + seconds
        self.setTimer(TIMER_MS)

    def onTimer(self):
        before = (self.state.revision, self.state.candidate, self.state.question, self.state.status, self.state.failed)
        self.poll_results()
        after = (self.state.revision, self.state.candidate, self.state.question, self.state.status, self.state.failed)
        if after != before or (not self.state.live and self.state.panel() != getattr(self, "panel_shown", None)):
            self.publish()  # an answer, a question, progress, or the pause for compose's keys
        # Still waiting: an instruction or rewrite that is working, or a suggestion not yet back.
        waiting = self.state.working or (after == before and time.monotonic() < getattr(self, "waiting_until", 0))
        if waiting:
            self.setTimer(TIMER_MS)

    def filterKeyUp(self, event):
        # PIME can only change what is shown in reply to a request. In continue Claudish takes the
        # key-downs of printable keys (it commits them itself), so it takes their key-ups too: the
        # onKeyUp reply carries an edit session, and with it the suggestion.
        # Likewise Tab's key-up while a rewrite it asked for is on its way: it often is by then.
        # A Shift tap switches mode; its key-up is taken so onKeyUp, with an edit session, can commit
        # what you composed.
        if event.keyCode == 0x10 and self.keyboardOpen and not self.sensitive():
            # PIME asks twice for one key-up (TSF's test, then the key itself): the second answer
            # must match the first.
            if self.shift.down_at is not None:
                self.switching = self.shift.release(time.monotonic(), chord=held_chord(event))
            keylog("filterKeyUp shift", "tap=%s" % getattr(self, "switching", False))
            return getattr(self, "switching", False)
        return bool(self.keyboardOpen and (self.state.live and event.isPrintableChar() or
                                           event.keyCode == 0x09 and self.state.asked == "rewrite"
                                           and self.state.working))

    def onKeyUp(self, event):
        self.poll_results()
        if getattr(self, "switching", False):
            self.switching = False
            self.switch_mode()
            return True
        self.publish()
        return True

    def poll_results(self):
        # PIME replies are event-driven: poll on a key event, never mutate TSF off-thread.
        if self.worker:
            self.state.offline = self.worker.offline  # the service stopped or came back
        result = self.worker.poll() if self.worker else None
        if result:
            revision, data = result
            if "text" in data:
                self.state.offer(revision, data["text"], data.get("candidates", ()))
            elif "question" in data:
                self.state.ask(revision, data["question"], data["session"])
            elif "progress" in data or "partial" in data:
                self.state.note(revision, data.get("progress") or data.get("partial"))
            elif "done" in data:
                if self.state.done(revision):
                    self.setToast(blank(status=data["done"]), 3)  # a helper took the task: said briefly at the caret
            elif "error" in data:
                self.state.fail(revision, data["error"])  # the panel says why: Enter retries

    def onKeyDown(self, event):
        if event.keyCode == 0x7B and self.preview():
            return True
        keylog("onKeyDown", hex(event.keyCode), "ctrl=%d" % event.isKeyDown(0x11), "len=%d" % len(self.state.text),
               "around=%s/%s" % tuple(len(s) for s in self.around()),
               "selected=%d" % len(getattr(self, "textSelected", None) or ""), "scopes=%s" % getattr(self, "inputScopes", None))
        self.poll_results()
        self.follow_document()
        key = event.keyCode
        if self.sensitive() and event.isPrintableChar() and not self.state.text:
            # The first key in a password field, taken before its kind was known: type it as is.
            self.setCommitString(chr(event.charCode))
            return True
        if self.shortcut(event):
            # Commit the wording and take the key (passing it on after the test phase said taken made
            # Edge drop the composition), then press it again for the app: one press does both.
            self.setCommitString(self.state.commit())
            self.changed()
            if key not in (0x11, 0x12, 0x5B, 0x5C):
                replay(key, held(event))
            return True
        if key == 0x0D and event.isKeyDown(0x10) and self.state.text and not self.state.live:
            self.setCommitString(self.state.keep())  # Shift+Enter: as it is, and keep composing
            self.changed()
            return True
        if key == 0x0D:
            action = self.state.enter()  # Enter talks to the model; it never inserts its text
            if action == "pass":  # nothing composed: the app's Enter, as it is (never replayed)
                return False
            if action == "choose":  # answer with the highlighted choice
                chosen = self.state.answer_choice()
                if chosen and self.worker:
                    self.worker.answer(*chosen)
                self.publish()
                return True
            if action == "reply":  # your own words, in answer to the agent's question
                session, question, words = self.state.answer_text()
                if self.worker:
                    self.worker.answer(session, question, text=words)
                self.publish()
                return True
            if action == "submit":
                self.state.submit()
                if self.worker:
                    before, after = self.around()  # the text box, for this turn of its conversation
                    self.worker.schedule(self.state.revision, self.state.text, "instruct", immediate=True,
                                         app=focused_app(), look=self.state.look, before=before, after=after,
                                         purpose=self.field())
                    self.await_result(60)
                self.publish()
                return True
            if action == "wait":  # still working, or the model's text: the panel lights Tab, which takes it
                self.publish()
                return True
        # Choices are not numbered: digits are text in English, as Space is (↑/↓ and Enter choose).
        if self.state.live and key != 0x77:  # F8 is handled below
            return self.live_key(event)
        if key == 0x77:  # F8 in instruct: send a picture of this window with the instruction.
            if self.state.toggle_look():
                self.publish()
            return bool(self.state.text)
        if key == 0x09:
            action = self.state.tab()
            if action == "choose":
                chosen = self.state.answer_choice()
                if chosen and self.worker:
                    self.worker.answer(*chosen)
                self.publish()
                return True
            if action == "request":  # rewrite: ask now; it waits in the panel when it arrives
                if self.worker:
                    before, after = self.around()  # where the rewrite goes
                    self.worker.schedule(self.state.revision, self.state.text, "rewrite", immediate=True,
                                         app=focused_app(), before=before[-1500:], after=after[:500],
                                         purpose=self.field())
                    self.await_result()
            if action != "accept":  # convert shows the rewrite in place; wait shows nothing new
                self.publish()
                return True
            self.setCommitString(self.state.commit(True))
        elif key in (0x26, 0x28) and self.state.move(-1 if key == 0x26 else 1):  # ↑ and ↓ move the highlight
            self.publish()
            return True
        elif key == 0x1B and event.isKeyDown(0x10) and self.state.restore():  # Shift+Esc: the dropped one, back
            if self.state.working and self.worker:  # held while it worked: ask again
                self.worker.schedule(self.state.revision, self.state.text, "instruct", immediate=True,
                                     app=focused_app(), purpose=self.field())
                self.await_result(60)
            self.publish()
            return True
        elif key == 0x1B:
            action = self.state.escape()
            if action == "dismiss":  # an answer to read: Dismiss, nothing inserted
                chosen = self.state.dismissal()
                if chosen and self.worker:
                    self.worker.answer(*chosen)
                self.publish()
                return True
            if action in ("clear", "drop"):  # words discarded: said, with the key that brings them back
                self.setToast(self.state.dropped_toast(), 2)
            if action == "clear":  # the reply goes; the question stays
                self.publish()
                return True
            if action != "keep":  # back: still composing; drop: nothing is inserted
                if self.worker:
                    self.worker.schedule(self.state.revision, "")  # stop a pending answer
                if action == "drop":
                    self.setCommitString("")
                self.publish()
                return True
            self.setCommitString(self.state.commit())
        elif key == 0x08:
            self.state.backspace()
        elif event.isPrintableChar() and self.state.passes(chr(event.charCode)):
            self.setCommitString(chr(event.charCode))  # nothing composed: the space is the app's text
        elif event.isPrintableChar():
            char = chr(event.charCode)
            if not self.state.insert(char):
                self.setCommitString(self.state.commit())
                self.state.insert(char)
        elif key in (0x10, 0x14):  # Shift / Caps Lock do not finish composition.
            self.publish()
            return True
        else:
            # A navigation key commits the wording, then reaches the app (replayed): one press does both.
            self.setCommitString(self.state.commit())
            self.changed()
            replay(key, held(event))
            return True
        self.changed()
        return True

    def live_key(self, event):
        """Continue mode: what filterKeyDown took (printable keys, Tab and Esc with a suggestion)."""
        key = event.keyCode
        if key == 0x09:
            ghost = self.state.take_ghost()
            if ghost:
                self.setCommitString(ghost)
        elif key == 0x1B:
            self.state.dismiss()
        elif event.isPrintableChar():
            if not self.state.text:  # a fresh start (a click, a paste, a new field): begin from the app's text
                self.state.change(self.around()[0][-MAX_COMPOSITION:])
            self.setCommitString(self.state.type_live(chr(event.charCode)))
        self.changed()
        return True

    def onCompositionTerminated(self, forced):
        keylog("onCompositionTerminated", "forced=%s" % forced, "len=%d" % len(self.state.text))
        super().onCompositionTerminated(forced)
        if self.state.live and not forced:
            return  # continue commits every key, which ends a composition: the context stays
        if self.state.sent:
            # The app ended the composition while an exchange was open (a click, a focus change,
            # another input method): TSF keeps what it showed (your own words, as a CJK preedit),
            # and the exchange is held for this box, offered on return. Parked too: switching to
            # another input method closes this instance, and the next one here takes it up.
            self.state.leave(getattr(self, "last_document", None))
            if self.worker:
                park(foreground(), self.state, self.worker)
            return
        self.state.change("")
        if self.worker:
            self.worker.schedule(self.state.revision, "")

    def onKeyboardStatusChanged(self, opened):
        super().onKeyboardStatusChanged(opened)
        self.keyboardOpen = opened
        if not opened:
            self.state.change("")
            self.changed()
