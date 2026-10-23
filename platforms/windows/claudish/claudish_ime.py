"""PIME/TSF adapter. Shared files are copied here by install.ps1."""
from textService import TextService
import time

from .composition import MAX_COMPOSITION, MODES, Composition, ShiftTap
from .client import Suggestions


def keylog(*fields):
    """Opt-in diagnostics: CLAUDISH_KEYLOG=path appends key routing events. Never logs typed text."""
    import os
    path = os.environ.get("CLAUDISH_KEYLOG")
    if path:
        try:
            with open(path, "a") as log:
                log.write(" ".join(str(field) for field in fields) + "\n")
        except OSError:
            pass


MODE_COMMAND = 100  # the input indicator's click; its menu items follow
# TSF input scopes (InputScope.h) by the names the service understands.
INPUT_SCOPES = {1: "url", 4: "email", 5: "email", 7: "name", 28: "digits", 29: "number",
                31: "password", 32: "phone", 33: "phone", 34: "phone", 35: "phone", 36: "phone"}
TIMER_MS = 100  # how often Claudish's PIME calls back while an answer is on its way


def mode_icon(mode):
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "mode-%s.ico" % mode)


def mode_tooltip(mode):
    return "cd_AI · %s (F7 switches mode)" % mode


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


class ClaudishTextService(TextService):
    def __init__(self, client):
        super().__init__(client)
        self.state = Composition()
        self.shift = ShiftTap()  # Shift alone, tapped: the mode switch
        self.worker = None

    def onActivate(self):
        if self.worker is None:
            self.worker = Suggestions()
        self.setKeyboardOpen(True)
        self.setSelKeys("123456789")
        # The mode in the taskbar's input indicator (PIME's Windows 8+ mode icon); its menu picks one.
        self.addButton("windows-mode-icon", icon=mode_icon(self.state.mode), commandId=MODE_COMMAND,
                       tooltip=mode_tooltip(self.state.mode))

    def switch_mode(self):
        """A Shift tap, or a click or pick on the input indicator: continue <-> compose. Leaving
        compose keeps what you see, as typed."""
        kept = self.state.toggle()
        if self.worker:
            self.worker.schedule(self.state.revision, "")  # what was asked belongs to the old mode
        self.setCommitString(kept)  # ends the composition; "" inserts nothing
        self.showMessage("cd_AI: " + self.state.mode, 2)
        self.changeButton("windows-mode-icon", icon=mode_icon(self.state.mode), tooltip=mode_tooltip(self.state.mode))
        self.changed()

    def onCommand(self, commandId, commandType):
        if commandId == MODE_COMMAND:  # a click on the indicator: the other mode, as a Shift tap
            self.switch_mode()
        elif MODE_COMMAND < commandId <= MODE_COMMAND + len(MODES):  # a pick from its menu
            if self.state.mode != MODES[commandId - MODE_COMMAND - 1]:
                self.switch_mode()

    def onMenu(self, buttonId):
        if buttonId != "windows-mode-icon":
            return None
        return [{"text": mode, "id": MODE_COMMAND + 1 + index, "checked": mode == self.state.mode}
                for index, mode in enumerate(MODES)]

    def onDeactivate(self):
        if self.worker:
            self.worker.close()
            self.worker = None
        self.state.change("")

    def sensitive(self):
        """A password field (IS_PASSWORD): cd_AI stays out, as IBus does for its password purpose."""
        return self.field() == "password"

    def follow_document(self):
        """One conversation per text box: Claudish's PIME names the TSF context of each request."""
        document = getattr(self, "document", None)
        if document and document != getattr(self, "last_document", None):
            if getattr(self, "last_document", None) is not None and self.worker:
                self.worker.new_conversation()
            self.last_document = document

    def filterKeyDown(self, event):
        keylog("filterKeyDown", hex(event.keyCode), "ctrl=%d" % event.isKeyDown(0x11), "len=%d" % len(self.state.text))
        if not self.keyboardOpen or self.sensitive():
            return False
        if event.keyCode == 0x10:  # Shift: perhaps a tap, the mode switch (seen at its key-up)
            self.shift.press(time.monotonic())
            return False
        self.shift.other()
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
            if event.keyCode == 0x75:  # F6 shows it (PIME cannot redraw without a key)
                return True
            # Continue types into the app. Tab and Esc are ours only while a suggestion shows;
            # Backspace, Enter, and navigation are the app's (the context follows here).
            if event.keyCode in (0x09, 0x1B):
                return bool(self.state.ghost)
            if event.isPrintableChar():
                return True
            if event.keyCode == 0x08:
                if self.state.text:
                    self.state.backspace()
                self.publish()
            elif event.keyCode not in (0x10, 0x14, 0x75, 0x77):
                self.drop_live()
            return False
        return event.isPrintableChar() or bool(self.state.text)

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
        if self.state.live:
            # Your words are in the app already; the suggestion shows in the candidate window
            # (TSF compositions cannot be greyed), and Tab takes it.
            self.setCompositionString("")
            ghost = self.state.ghost
            self.setCandidateList(["Tab: …" + ghost.lstrip()] if ghost else [])
            self.setShowCandidates(bool(ghost))
            return
        shown = self.state.shown  # rewrite after Tab: the rewrite, in place of your words
        self.setCompositionString(shown)
        # TSF cursor offsets count UTF-16 code units.
        self.setCompositionCursor(len(shown.encode("utf-16-le")) // 2)
        # A list only for an instruction's drafts or an agent's question; rewrite converts in place.
        if self.state.question:
            candidates = [c.get("label", "") + (" - " + c["legend"] if c.get("legend") else "")
                          for c in self.state.question.get("choices") or []]
        else:
            candidates = self.state.candidates if self.state.choosing else []
        self.setCandidateList(candidates)
        self.setShowCandidates(bool(candidates))

    def changed(self):
        self.state.quiet = self.field() in ("url", "email", "number", "phone", "digits")
        if self.worker and self.state.automatic:
            # Continue asks at once at a word boundary (itself the pause), so the answer is often
            # ready by the time the key is released, and onKeyUp can show it.
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=focused_app(),
                                 immediate=self.state.live, after=self.around()[1][:500], purpose=self.field())
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
        (onTimer) in an edit session. A stock PIME has no timer; the next key shows it then."""
        if hasattr(self, "setTimer"):
            self.waiting_until = time.monotonic() + seconds
            self.setTimer(TIMER_MS)

    def onTimer(self):
        before = (self.state.revision, self.state.candidate, self.state.question, self.state.status, self.state.failed)
        self.poll_results()
        after = (self.state.revision, self.state.candidate, self.state.question, self.state.status, self.state.failed)
        if after != before:
            self.publish()
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
            self.switching = self.shift.release(time.monotonic())
            keylog("filterKeyUp shift", "tap=%s" % self.switching)
            return self.switching
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
        result = self.worker.poll() if self.worker else None
        if result:
            revision, data = result
            if "text" in data:
                self.state.offer(revision, data["text"], data.get("candidates", ()))
            elif "question" in data:
                if self.state.ask(revision, data["question"], data["session"]):
                    self.showMessage("cd_AI asks: %s (1-%d)" % (data["question"].get("text", ""),
                                                                len(data["question"].get("choices") or [])), 5)
            elif "progress" in data or "partial" in data:
                if self.state.note(revision, data.get("progress") or data.get("partial")):
                    self.showMessage("cd_AI: " + " ".join(self.state.status.split())[-60:], 2)
            elif "error" in data:
                self.state.fail(revision)
                if self.state.failed:
                    self.showMessage("cd_AI: the request failed; Enter sends it again", 3)

    def onKeyDown(self, event):
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
            # Commit the wording and consume the key; pressing the shortcut again runs it. Passing
            # it on (not eaten after the test phase said eaten) made Edge drop the composition.
            self.setCommitString(self.state.commit())
            self.changed()
            return True
        if key == 0x0D and event.isKeyDown(0x10) and self.state.text and not self.state.live:
            self.setCommitString(self.state.keep())  # Shift+Enter: as it is, and keep composing
            self.changed()
            return True
        if key == 0x0D:
            # Instruct holds the text until Enter sends it; the next Enter inserts the result.
            action = self.state.enter()
            if action == "reply":  # your own words, in answer to the agent's question
                session, question, words = self.state.answer_text()
                if self.worker:
                    self.worker.answer(session, question, text=words)
                self.showMessage("cd_AI: " + self.state.status, 2)
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
                self.showMessage("cd_AI: working… Enter inserts the result when ready", 3)
                self.publish()
                return True
            if action == "wait":
                self.showMessage("cd_AI: still working…", 2)
                return True
        if self.state.question and not self.state.reply and 0x31 <= key <= 0x39:  # an agent's question: the digit is the answer
            chosen = self.state.answer_choice(key - 0x30)
            if chosen and self.worker:
                self.worker.answer(*chosen)
                self.showMessage("cd_AI: " + self.state.status, 2)
            self.publish()
            return True
        if self.state.choosing and not self.state.question and 0x31 <= key <= 0x39:  # 1-9 pick from the list, as in CJK input methods
            text = self.state.pick(key - 0x30)
            if text is not None:
                self.setCommitString(text)
                self.changed()
            return True
        if self.state.live and key != 0x77:  # F8 is handled below
            return self.live_key(event)
        if key == 0x75:  # F6 previews the ready candidate without committing it.
            self.publish()
            return True
        if key == 0x77:  # F8 in instruct: send a picture of this window with the instruction.
            if self.state.toggle_look():
                self.showMessage("cd_AI: " + ("the window picture goes with this instruction" if self.state.look
                                              else "no window picture"), 2)
                self.publish()
            return bool(self.state.text)
        if key == 0x09:
            action = self.state.tab()
            if action == "request":  # rewrite: ask now; it converts in place when it arrives
                if self.worker:
                    before, after = self.around()  # where the rewrite goes
                    self.worker.schedule(self.state.revision, self.state.text, "rewrite", immediate=True,
                                         app=focused_app(), before=before[-1500:], after=after[:500],
                                         purpose=self.field())
                    self.await_result()
                self.showMessage("cd_AI: rewriting…", 2)
            if action != "accept":  # convert shows the rewrite in place; wait shows nothing new
                self.publish()
                return True
            self.setCommitString(self.state.commit(True))
        elif key == 0x1B:
            action = self.state.escape()
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
        elif key == 0x0D:
            # Enter reaches here only with a result to take (see above).
            self.setCommitString(self.state.commit(True))
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
            # First navigation key commits; a second performs navigation.
            self.setCommitString(self.state.commit())
        self.changed()
        return True

    def live_key(self, event):
        """Continue mode: what filterKeyDown took (printable keys, Tab and Esc with a suggestion)."""
        key = event.keyCode
        if key == 0x75:
            self.publish()
            return True
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
        self.state.change("")
        if self.worker:
            self.worker.schedule(self.state.revision, "")

    def onKeyboardStatusChanged(self, opened):
        super().onKeyboardStatusChanged(opened)
        self.keyboardOpen = opened
        if not opened:
            self.state.change("")
            self.changed()
