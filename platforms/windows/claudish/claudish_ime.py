"""PIME/TSF adapter. Shared files are copied here by package.py (platforms/windows)."""
from textService import TextService
import json
import os
import time
import weakref

from .composition import HELD_SECONDS, MAX_COMPOSITION, MODES, Composition, ShiftTap, window
from .client import Suggestions
from .screen import is_terminal


def keylog(*fields):
    """Opt-in diagnostics: CLAUDISH_KEYLOG=path appends key routing events."""
    path = os.environ.get("CLAUDISH_KEYLOG")
    if path:
        try:
            with open(path, "a") as log:
                log.write(" ".join(str(field) for field in fields) + "\n")
        except OSError:
            pass


MODE_COMMAND = 100  # the input indicator's click; its menu items follow
SETTINGS_COMMAND = 200  # Settings… in that menu
# TSF input scopes (InputScope.h, Windows SDK 10.0.22621) by the names the service understands; a PIN
# or numeric password is a password, as IBus's PIN purpose is on Linux.
INPUT_SCOPES = {1: "url", 4: "email", 5: "email", 7: "name", 28: "digits", 29: "number", 31: "password",
                32: "phone", 33: "phone", 34: "phone", 35: "phone",
                63: "password", 64: "password", 65: "password", 66: "password"}
TIMER_MS = 100  # how often Claudish's PIME calls back while an answer is on its way


def mode_icon(mode):
    """The taskbar's mode icon: continue's cream "cd" tile or compose's "AI", the same in both themes."""
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
# The held exchange's pill waits for your next key (which hides any toast), as on macOS and Linux:
# as long as the exchange is held.
PILL_SECONDS = 600
INSTANCES = weakref.WeakSet()  # the live instances: a parked worker one still uses is not closed
UNSEEN = object()  # an instance that has not looked for a parked exchange since it was activated


def park(window, state, worker):
    expire()
    replaced = PARKED.get(window)
    if replaced is not None and replaced[1] is not worker:
        release(replaced[1])
    PARKED[window] = (state, worker, time.monotonic())


def release(worker):
    """A parked worker no instance uses any more ends: its polling thread, and the agent session it held."""
    if not any(getattr(instance, "worker", None) is worker for instance in list(INSTANCES)):
        worker.close()


def gone(box):
    worker = box[0]
    if worker is not None and not any(parked[1] is worker for parked in PARKED.values()):
        release(worker)


def expire():
    for window, (_, worker, when) in list(PARKED.items()):
        if time.monotonic() - when > HELD_SECONDS:
            del PARKED[window]
            release(worker)


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


# A console window (conhost, whatever program it runs: wsl, ssh, python) and Windows Terminal: a
# terminal by its window, where the process would name only the program inside.
CONSOLE_CLASSES = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow")


def console_window():
    """Whether the foreground window is a console's or Windows Terminal's."""
    try:
        import ctypes
        name = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(ctypes.windll.user32.GetForegroundWindow(), name, 256)
        return name.value in CONSOLE_CLASSES
    except (AttributeError, OSError):
        return False


STEPS = {0x25: -1, 0x27: 1, 0x24: "home", 0x23: "end"}  # ← → Home End, inside what you type
# Keys sent with KEYEVENTF_EXTENDEDKEY: PgUp to Down, Insert, Delete, the Windows keys, keypad /.
EXTENDED_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5C, 0x6F}


MODIFIER_KEYS = (0x10, 0x11, 0x12, 0x5B)  # Shift, Ctrl, Alt, Windows
# The left and right ones too: AltGr arrives as a key-down of left Ctrl (0xA2), then right Alt.
SIDED_KEYS = (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)
CHORD_KEYS = (0x11, 0x12, 0x5B, 0x5C)  # Ctrl, Alt, left and right Windows: with a key, a shortcut
SELECTING = (0x10, 0x11, 0x12)  # Shift, Ctrl, Alt: with an arrow or Delete, the app's (selection, words)


def plain_tab(event):
    """Tab without Shift (Shift+Tab is the app's)."""
    return event.keyCode == 0x09 and not event.isKeyDown(0x10)


def held_chord(event):
    """Ctrl, Alt or Win down with Shift: Windows' layout and language switch, not a Shift tap. Or a
    mouse button pressed since the last look (Shift+click selects): a click sends no key."""
    return any(event.isKeyDown(key) for key in CHORD_KEYS) or clicked()


def clicked():
    """A mouse button down, or pressed since the last call (GetAsyncKeyState's low bit; the first
    call, at Shift's press, clears it). False when it cannot tell (not on Windows)."""
    try:
        import ctypes
        state = ctypes.windll.user32.GetAsyncKeyState
        return any([state(button) & 0x8001 for button in (0x01, 0x02, 0x04)])  # all three read: each clears
    except (AttributeError, OSError):
        return False


def held(event):
    """The modifiers down with this key."""
    return [key for key in MODIFIER_KEYS if event.isKeyDown(key)]


def replay(vk, modifiers=()):
    """The reply's "replay": the key pressed again for the app just after cd_AI commits what was
    composed, so one press of a shortcut or navigation key both commits and acts. cd_AI's PIME sends
    it from the app's own process (where an app running as administrator accepts it), after the
    commit; a modifier that was down with it and is up by then (a quick tap) is pressed with it again.
    Nothing is composed by then, so cd_AI lets it through. Each key is [code, extended]."""
    return {"key": [vk, vk in EXTENDED_KEYS], "modifiers": [[key, key in EXTENDED_KEYS] for key in modifiers]}


def focused_app():
    """The foreground window's program name (for bindings), such as "notepad.exe"; None elsewhere."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        pid = foreground()
        if not pid:
            return None
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
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
    """cd_AI's settings in the browser (claudish.client.show_settings); no service: nothing to open,
    doctor says why."""
    import webbrowser
    from .client import show_settings
    show_settings(webbrowser.open)


class ClaudishTextService(TextService):
    def __init__(self, client):
        super().__init__(client)
        INSTANCES.add(self)
        # PIME drops an instance whose app's connection closed without onDeactivate: its worker ends
        # with it (its threads, its conversations), unless it is parked for the next one here. The
        # finalizer holds only the worker's box, nothing that leads back to the instance (PIME's
        # client does), or the instance could never be collected.
        self._worker = [None]
        weakref.finalize(self, gone, self._worker)
        self.state = Composition()
        if LAST_MODE[0] and LAST_MODE[0] != self.state.mode:
            self.state.mode = LAST_MODE[0]  # back to cd_AI from another input method: the same mode
        self.shift = ShiftTap()  # Shift alone, tapped: the mode switch
        self.worker = None
        self.adopted_from = UNSEEN
        self.last_document = None  # the text box of the last request (follow_document)
        self.taken_keys = set()  # continue's key-downs taken: their key-ups are taken too, only theirs
        self.drawn_ghost = ""  # the suggestion last drawn: Tab and Esc are cd_AI's only for one you see
        self.owner = None  # this instance's app (its process, in front at its first request): parks go there
        self.switching = False  # a Shift tap switched modes: its key-up is taken
        self.committed = False  # the last reply committed: PIME's end of the composition is that commit's
        self.panel_shown = None  # the panel as last published
        self.waiting_until = 0  # an answer awaited: the timer looks for it until then (await_result)
        self.previews = None  # the design lab's states (the gallery's preview)
        self.known_scopes = None  # the text box's input scopes, kept from the request that carried them

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
        spec, lasting = self.state.switched()
        if spec:  # the mode switch briefly, or the held exchange's pill
            self.setToast(spec, PILL_SECONDS if lasting else 2)
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
        keylog("onDeactivate", id(self), "sent=%s held=%s" % (self.state.for_model, len(self.state.holds)))
        if self.state.for_model:
            self.state.leave(self.last_document)
        if self.worker and (self.state.holds or self.state.dropped):
            park(self.owner or foreground(), self.state, self.worker)  # something to come back to
            self.worker = None
            self.state = Composition()
            self.state.mode = LAST_MODE[0] or self.state.mode  # back to cd_AI: the mode you were in
        elif self.worker:
            for window, parked in list(PARKED.items()):  # parked at a click, and taken up again since
                if parked[1] is self.worker:
                    del PARKED[window]
            self.worker.close()
            self.worker = None
        self.state.change("")
        self.adopted_from = UNSEEN  # activated again (this instance or a new one): look for it again

    def adopt_parked(self):
        """At the first request after activation: this window's parked exchange and worker, if any."""
        for each, parked in list(PARKED.items()):  # parked at a click while this instance went on with it:
            if parked[0] is self.state:  # this instance's, not a copy for the next one to take
                del PARKED[each]
        window = foreground()
        if window:  # this instance's app: in front at its first request (keys come only to it)
            self.owner = window
        if self.adopted_from == window:
            return
        expire()
        parked = PARKED.get(window)
        keylog("adopt", id(self), window, "found=%s" % (parked is not None))
        if parked is None or parked[1] is self.worker:
            self.adopted_from = window
            return
        # Held for a text box: taken up there (the next instance in that box, after an input-method
        # switch), not in another window's (the instance that parked it at the click goes on with it);
        # looked at again at the next request. A key names no box: the one focus last said is checked.
        if any(other is not self and other.isActivated and getattr(other, "worker", None) is parked[1]
               for other in list(INSTANCES)):
            return  # still in use by the instance that parked it (another window of this app)
        document, held = getattr(self, "document", None) or self.last_document, parked[0]
        boxes = set(held.holds) | ({held.dropped_box} if held.dropped_box else set())
        if document is not None and boxes and document not in boxes:
            return
        self.adopted_from = window
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
        if document and document != self.last_document:
            if self.state.for_model:  # an instruction's exchange, left in the other text box: held for it
                self.state.leave(self.last_document)
            elif self.state.live and self.state.text:  # continue's context and suggestion were the other box's
                self.drop_live()
            if self.worker:
                self.worker.use_conversation(document)  # this box's own, also when you come back to it
            self.last_document = document
            self.known_scopes = None  # another text box: its own scopes (a password field's stay behind)
            pill = self.state.returned(document)  # back where one was held: a pill, taking no keys
            if pill:
                self.setToast(pill, PILL_SECONDS)

    def preview(self):
        """Screenshot plumbing: with the design lab's
        states at PREVIEW, each F12 draws the next one with the real panel, to compare with the lab.
        Without that file F12 is the app's."""
        if not os.path.exists(PREVIEW):
            return False
        if self.previews is None:
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
        keylog("filterKeyDown", hex(event.keyCode), "ctrl=%d alt=%d char=%x" % (event.isKeyDown(0x11), event.isKeyDown(0x12), event.charCode),
               "len=%d" % len(self.state.text))
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
        # Modifiers, the lock keys (a replay would toggle them back) and VK_PACKET (a character another
        # program sends, which a replay would not carry) are the system's, never taken.
        if event.keyCode in (0x11, 0x12, 0x14, 0x5B, 0x5C, 0x90, 0x91, 0xE7) + SIDED_KEYS:
            return False
        # AltGr arrives as Ctrl+Alt; a printable result is typing, not a shortcut.
        if self.shortcut(event):
            if self.state.live:  # nothing is held back in continue mode
                self.drop_live()
                return False
            # Mid-composition, take the key so onKeyDown commits the wording. Left to TSF, the
            # composition was discarded (Ctrl+A lost the typed text).
            return bool(self.state.text)
        # A dead key is Windows' too: its accent waits for the next key, which brings the accented
        # letter (é from ´ then e), and the composition goes on.
        if getattr(event, "isDead", False):
            return False
        if self.state.live:
            self.poll_results()  # a waiting suggestion decides whether Tab is ours
            # Continue types into the app. Tab and Esc are ours only while a suggestion shows;
            # Backspace, Enter, and navigation are the app's (the context follows here).
            if event.keyCode == 0x1B and getattr(event, "charCount", 1) > 1:
                return True  # right after a dead key: Esc takes back the accent, and only it
            if event.keyCode == 0x1B or plain_tab(event):  # Shift+Tab: the app's
                if self.state.ghost and not self.caret_stayed():  # a click moved it: Tab never takes one gone
                    self.drop_live()
                    return False
                return bool(self.state.ghost) and self.state.ghost == self.drawn_ghost  # one you see
            if event.isPrintableChar():
                self.taken_keys.add(event.keyCode)
                return True
            # Backspace, Enter, navigation: the app's. The context starts over from the app's text at
            # the next key (this runs twice per key, in TSF's test and again for the key itself, so
            # it changes nothing that a second run would change again).
            if event.keyCode not in (0x10, 0x14, 0x77):
                self.drop_live()
            return False
        # An accent that does not combine with this key, then the key's own character ('t after ' on
        # US-International): the app types both into the composition, and Claudish's PIME sends them
        # as typed. Backspace, Tab, Enter and Esc stay Claudish's keys (the accent goes).
        if getattr(event, "charCount", 1) > 1 and event.keyCode not in (0x08, 0x09, 0x0D, 0x1B):
            return False
        return self.ours(event)

    def ours(self, event):
        """Whether cd_AI takes this key while composing (not continue)."""
        # Shift+Esc with nothing composed: the exchange you left, or the instruction Esc dropped, comes back.
        restoring = event.keyCode == 0x1B and event.isKeyDown(0x10) and self.state.restorable()
        taking = plain_tab(event) and bool(self.selection())  # Tab on a selection: your words
        return event.isPrintableChar() or bool(self.state.text) or restoring or taking

    def caret_stayed(self):
        """Whether the text before the caret is still what continue typed (a click in the same field
        sends no key: macOS looks at the caret for the same reason). True without the text (a stock PIME)."""
        return self.state.caret_stayed(self.around()[0])

    def selection(self):
        """The app's selected text when nothing is composed (Claudish's PIME sends it), if it fits."""
        selected = getattr(self, "textSelected", None) or ""
        return selected if not self.state.text and not self.state.live and self.state.selectable(selected) else ""

    def drop_live(self):
        self.state.change("")
        if self.worker:
            self.worker.schedule(self.state.revision, "")
        self.publish()

    def shortcut(self, event):
        typing = event.isPrintableChar() or getattr(event, "isDead", False) or getattr(event, "charCount", 1) > 1
        altgr = (event.isKeyDown(0x11) and event.isKeyDown(0x12) and typing
                 and not (event.isKeyDown(0x5B) or event.isKeyDown(0x5C)))
        return not altgr and any(event.isKeyDown(key) for key in CHORD_KEYS)

    def publish(self):
        """The screen from the state, in Claudish's PIME (platforms/windows/pime): continue's
        suggestion right after the caret, or the panel Composition.panel() describes (drawn as the
        design lab's Windows 11 mock), and in compose your words as the composition."""
        if self.state.live:
            # Your words are in the app already; the suggestion is cd_AI's own grey text after the
            # caret, and Tab takes it.
            self.setCompositionString("")
            if self.state.ghost and not self.caret_stayed():  # a click (or the app's autocorrect) moved the text:
                self.drop_live()  # not drawn over it, and continue starts again from the app's text
                return
            self.drawn_ghost = "" if self.state.inside else self.state.ghost
            self.setGhost(self.drawn_ghost)
            self.setPanel(None)
            self.setCandidateList([])
            self.setShowCandidates(False)
            return
        self.drawn_ghost = ""
        self.setGhost("")
        # A sent instruction is not text for the app: if the app ends the composition (a focus change),
        # Claudish's PIME clears it; words still being typed stay, as a CJK preedit does.
        self.setClearOnEnd(self.state.for_model)
        shown = self.state.shown  # your words (a rewrite waits in the panel for Tab)
        self.setCompositionString(shown)
        # The cursor, where ← and → left it, in characters: PIME turns it into TSF's UTF-16 offset.
        self.setCompositionCursor(self.state.cursor)
        panel = self.state.panel()
        self.setPanel(panel)
        # The rows also go to TSF's candidate list, for apps that draw candidates themselves.
        self.setCandidateList([row["text"] for row in panel["rows"]] if panel else [])
        self.setShowCandidates(bool(panel))
        self.panel_shown = panel

    def changed(self):
        # Not prose: a URL, an address, a number, or a terminal's command line.
        self.state.field(self.field(), is_terminal(focused_app()))
        after = self.state.caret_after(self.around()[1] if self.state.live else "")
        if self.worker and self.state.automatic:
            # Continue asks at once at a word boundary (itself the pause), so the answer is often
            # ready by the time the key is released, and onKeyUp can show it.
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=focused_app(),
                                 immediate=self.state.live, after=after, purpose=self.field())
            self.await_result()
        elif self.worker and not self.state.text:
            self.worker.schedule(self.state.revision, "")
        self.publish()

    def field(self):
        """The field's kind from the input scopes the app declares (Claudish's PIME), as the
        service names them; None for prose or when unknown."""
        if getattr(self, "inputScopes", None) is not None:  # only requests with an edit session carry them
            self.known_scopes = self.inputScopes
        for scope in self.known_scopes or ():
            if scope in INPUT_SCOPES:
                return INPUT_SCOPES[scope]
        return "terminal" if console_window() else None

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
        away = self.owner and foreground() not in (None, self.owner)
        changed = self.poll_results(away)
        if away:
            pass  # another app is in front: nothing is drawn over it; onSetFocus shows it all on return
        elif changed or (not self.state.live and self.state.panel() != self.panel_shown):
            self.publish()  # an answer, a question, progress, or the pause for compose's keys
        # Still waiting: an instruction or rewrite that is working, or a suggestion not yet back.
        waiting = self.state.working or (not changed and time.monotonic() < self.waiting_until)
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
            if self.shift.down:  # the first of the two
                self.switching = self.shift.release(time.monotonic(), chord=held_chord(event))
            keylog("filterKeyUp shift", "tap=%s" % self.switching)
            return self.switching
        # A shortcut's key-up goes where its key-down went (to the app): only typing's are continue's.
        return bool(self.keyboardOpen and (event.keyCode in self.taken_keys or
                                           plain_tab(event) and self.state.asked == "rewrite"
                                           and self.state.working))

    def onKeyUp(self, event):
        self.taken_keys.discard(event.keyCode)
        self.poll_results()
        if self.switching:
            self.switching = False
            self.switch_mode()
            return True
        self.publish()
        return True

    def poll_results(self, away=False):
        """The worker's result, if any, in the composition: its kind when it changed what shows.
        away: another app is in front, where nothing is said (a helper's new window, often)."""
        # PIME replies are event-driven: poll on a key event, never mutate TSF off-thread.
        if self.worker:
            self.state.follow(self.worker)  # the config's keys, and whether the service answers
        result = self.worker.poll() if self.worker else None
        kind = self.state.receive(*result) if result else None
        toast = self.state.done_toast(result[1]["done"]) if kind == "done" else None
        if toast and not away:
            self.setToast(toast, 3)
        return kind

    def onKeyDown(self, event):
        if event.keyCode == 0x7B and self.preview():
            return True
        keylog("onKeyDown", hex(event.keyCode), "ctrl=%d alt=%d char=%x" % (event.isKeyDown(0x11), event.isKeyDown(0x12), event.charCode),
               "len=%d" % len(self.state.text),
               "around=%s/%s" % tuple(len(s) for s in self.around()),
               "selected=%d" % len(getattr(self, "textSelected", None) or ""), "scopes=%s" % getattr(self, "inputScopes", None))
        composing = bool(self.state.text)
        self.poll_results()
        self.follow_document()
        key = event.keyCode
        if composing and not self.state.text and not self.state.live and not self.ours(event):
            # A result at this key emptied the composition (a helper took the task): the key is the
            # app's after all, as on Linux and macOS, which poll at the key too.
            self.publish()
            return False
        if self.sensitive() and event.isPrintableChar() and not self.state.text:
            # The first key in a password field, taken before its kind was known: type it as is.
            self.setCommitString(chr(event.charCode))
            return True
        if self.shortcut(event):
            # Commit the wording and take the key (passing it on after the test phase said taken made
            # Edge drop the composition), then press it again for the app: one press does both. A sent
            # instruction is not text for the app: it is cleared and its exchange held for Shift+Esc,
            # as a focus change does (and as on Linux and macOS).
            if self.state.for_model:
                self.state.leave(self.last_document)
                self.publish()
            else:
                self.setCommitString(self.state.commit())
                self.changed()
            if key not in CHORD_KEYS + SIDED_KEYS:
                self.currentReply["replay"] = replay(key, held(event))
            return True
        shift = event.isKeyDown(0x10)
        if key == 0x0D and not self.state.talks(shift) and self.state.text and not self.state.live:
            kept = self.state.keep()  # the keeper key: as it is, and keep composing
            if kept is None:  # the model is asked: taken, nothing goes in
                self.publish()
                return True
            self.setCommitString(kept)
            self.changed()
            return True  # Enter commits, as other input methods do: press it again for the app
        if key == 0x0D:
            action = self.state.enter()  # the summon key talks to the model; it never inserts its text
            if action == "pass":  # nothing composed: the app's key, as it is (never replayed)
                return False
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
                                         purpose=self.field(), draft=self.state.about)
                    self.await_result(60)
                self.publish()
                return True
            if action == "wait":  # still working, or the model's text: the panel lights Tab, which takes it
                self.publish()
                return True
        # Choices are not numbered: digits are text in English, as Space is (↑/↓, then Tab).
        if self.state.live and key != 0x77:  # F8 is handled below
            return self.live_key(event)
        if key == 0x77:  # F8 while composing: a picture of this window goes with the instruction.
            if self.state.toggle_look():
                self.publish()
            return bool(self.state.text)
        if key == 0x09 and not event.isKeyDown(0x10):  # Shift+Tab commits and is the app's, as a navigation key
            if not self.state.text and self.selection():
                # The selection becomes your words, as if you had just typed them: the composition
                # takes its place, as typing does; then Tab rewrites it, Shift+Enter sends it.
                self.state.change(self.selection())
                self.publish()
                return True
            action = self.state.tab()
            if action == "choose":
                chosen = self.state.answer_choice()
                if chosen and self.worker:
                    self.worker.answer(*chosen)
                self.publish()
                return True
            if action == "request":  # rewrite: ask now; it waits in the panel when it arrives
                if self.worker:
                    before, after = window(*self.around())  # where the rewrite goes, as much as it sends
                    self.worker.schedule(self.state.revision, self.state.text, "rewrite", immediate=True,
                                         app=focused_app(), before=before, after=after,
                                         purpose=self.field())
                    self.await_result()
            if action != "accept":  # convert shows the rewrite in the panel; wait shows nothing new
                self.publish()
                return True
            answering = self.state.take_answering()  # an answer to read: recorded, not asked again
            if answering and self.worker:
                self.worker.answer(*answering)
            self.setCommitString(self.state.commit(True))
        elif key in (0x26, 0x28) and self.state.move(-1 if key == 0x26 else 1):  # ↑ and ↓ move the highlight
            self.publish()
            return True
        elif key == 0x1B and event.isKeyDown(0x10) and self.state.restore():  # Shift+Esc: the dropped one, back
            # A held exchange's request is still running: its results come for the same revision.
            if self.state.working:
                self.await_result(60)
            self.publish()
            return True
        elif key == 0x1B and getattr(event, "charCount", 1) > 1:
            pass  # right after a dead key: Esc takes back the accent (PIME uses it up), nothing else
        elif key == 0x1B and event.isKeyDown(0x10) and self.state.text:
            return True  # composing, Shift+Esc brings nothing back, and never drops what you typed
        elif key == 0x1B:
            action = self.state.escape()
            if action == "dismiss":  # an answer to read: Dismiss, nothing inserted
                chosen = self.state.dismissal()
                if chosen and self.worker:
                    self.worker.answer(*chosen)
                self.publish()
                return True
            toast = self.state.dropped_toast() if action in ("clear", "drop") else None
            if toast:  # words discarded: said, with the key that brings them back
                self.setToast(toast, 2)
            if action == "clear":  # the reply goes; the question stays
                self.publish()
                return True
            # back: still composing; drop: nothing is inserted
            if self.worker:
                self.worker.schedule(self.state.revision, "")  # stop a pending answer
            if action == "drop":
                self.setCommitString("")
            self.publish()
            return True
        elif key == 0x08 and getattr(event, "charCount", 1) > 1:
            pass  # right after a dead key: Backspace takes back the accent (PIME uses it up), nothing else
        elif key == 0x08:
            self.state.backspace()
        elif key in STEPS and not any(event.isKeyDown(k) for k in SELECTING) \
                and self.state.arrow(STEPS[key]):  # ← → Home End move in what you type (Shift+← selects)
            pass
        elif key == 0x2E and not any(event.isKeyDown(k) for k in SELECTING) \
                and self.state.delete():  # forward delete, at the cursor (Shift+Delete cuts)
            pass
        elif event.isPrintableChar() and self.state.passes(chr(event.charCode)):
            self.setCommitString(chr(event.charCode))  # nothing composed: the space is the app's text
        elif event.isPrintableChar():
            char = chr(event.charCode)
            if not self.state.insert(char):  # full: what is before the cursor goes in
                self.setCommitString(self.state.make_room(char))
        else:
            # A navigation key commits the wording, then reaches the app (replayed): one press does both.
            # What is for the model never goes in: the exchange is held, as on a focus change.
            if self.state.for_model:
                self.state.leave(self.last_document)
            else:
                self.setCommitString(self.state.commit())
            self.changed()
            self.currentReply["replay"] = replay(key, held(event))
            return True
        self.changed()
        return True

    def live_key(self, event):
        """Continue mode: what filterKeyDown took (printable keys, Tab and Esc with a suggestion)."""
        key = event.keyCode
        if key == 0x09 and not event.isKeyDown(0x10):
            ghost = self.state.take_ghost()
            if ghost:
                self.setCommitString(ghost)
        elif key == 0x1B and getattr(event, "charCount", 1) > 1:
            pass  # the accent only (PIME uses it up); the suggestion stays
        elif key == 0x1B:
            self.state.dismiss()
        elif event.isPrintableChar():
            # A fresh start (a paste, a new field), or a click since (Windows says nothing of it): from the app's text.
            if not self.state.text or not self.caret_stayed():
                self.state.change(self.around()[0][-MAX_COMPOSITION:])
            self.setCommitString(self.state.type_live(chr(event.charCode)))
        self.changed()
        return True

    @property
    def worker(self):
        return self._worker[0]

    @worker.setter
    def worker(self, worker):
        self._worker[0] = worker

    def handleRequest(self, msg):
        if msg.get("method") != "onCompositionTerminated":
            self.committed = False  # a commit of this request ends the composition: see below
        if msg.get("typed"):
            self.type_outside(msg["typed"])
        return super().handleRequest(msg)

    def type_outside(self, text):
        """What the app put into the composition at the cursor itself (an AltGr character, an Alt
        code: TSF gives those keys to no input method), as if it was typed (Claudish's PIME)."""
        for char in text:
            if not self.state.insert(char):  # full: what is before the cursor goes in
                self.setCommitString(self.state.make_room(char))
        self.publish()

    def setCommitString(self, text):
        self.committed = True
        super().setCommitString(text)

    def onCompositionTerminated(self, forced):
        keylog("onCompositionTerminated", "forced=%s" % forced, "len=%d" % len(self.state.text))
        super().onCompositionTerminated(forced)
        self.shift.cancel()  # the app ended it (a click): a Shift released next is not a tap
        if not forced and self.committed:
            # PIME ends the composition to put in what the last reply committed, and says so before
            # it shows that reply's composition: what stays composed (the words after a full
            # composition's commit, a reply on a draft Tab took) is not ended with it.
            self.committed = False
            return
        if self.state.live and not forced:
            return  # continue commits every key, which ends a composition: the context stays
        if self.state.for_model:
            # The app ended the composition while an exchange was open (a click, a focus change,
            # another input method): TSF keeps what it showed (your own words, as a CJK preedit),
            # and the exchange is held for this box, offered on return. Parked too: switching to
            # another input method closes this instance (with no onDeactivate), and the next one
            # here takes it up.
            self.state.leave(self.last_document)
            if self.worker:
                # Its own app's: the one in front now may be where the click went.
                park(self.owner or foreground(), self.state, self.worker)
            return
        self.state.change("")
        if self.worker:
            self.worker.schedule(self.state.revision, "")

    def onSetFocus(self):
        """The app has the keyboard again (Claudish's PIME sends it in an edit session): an exchange
        held for this text box says so at once, rather than at the next key."""
        keylog("onSetFocus", getattr(self, "document", None))
        self.taken_keys.clear()  # a key held while focus went: its key-up went elsewhere
        self.shift.cancel()  # focus moved (a Shift+click): its Shift is not a tap
        self.follow_document()
        self.field()  # this request carries the field's scopes: a key in a password field is not ours
        self.poll_results()  # what came while the app was in the background: the pill says it
        if self.state.working or time.monotonic() < self.waiting_until:
            # Still awaited: a timer that fired with no text box in focus stopped; the answer shows
            # when it comes, not at your next key.
            self.setTimer(TIMER_MS)
        pill = self.state.returned(getattr(self, "document", None))
        if pill:
            self.setToast(pill, PILL_SECONDS)
        else:
            # The panel as it is now (an answer that came meanwhile: Tab takes what you see), or an
            # instruction a helper finished while another app was in front, no longer composed.
            self.publish()

    def onKeyboardStatusChanged(self, opened):
        super().onKeyboardStatusChanged(opened)
        self.keyboardOpen = opened
        if not opened:  # as a focus change: your words go in, an open exchange is held
            held = self.state.for_model
            words = self.state.leave(self.last_document)
            if words:
                self.setCommitString(words)
            self.changed()
            if held:  # PIME ends the composition after this reply: the instruction is cleared, not kept
                self.setClearOnEnd(True)
