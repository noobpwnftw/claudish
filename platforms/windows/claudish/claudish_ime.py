"""PIME/TSF adapter. Shared files are copied here by install.ps1."""
from textService import TextService
from .composition import Composition
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
        self.worker = None

    def onActivate(self):
        if self.worker is None:
            self.worker = Suggestions()
        self.setKeyboardOpen(True)
        self.setSelKeys("123456789")

    def onDeactivate(self):
        if self.worker:
            self.worker.close()
            self.worker = None
        self.state.change("")

    def filterKeyDown(self, event):
        keylog("filterKeyDown", hex(event.keyCode), "ctrl=%d" % event.isKeyDown(0x11), "len=%d" % len(self.state.text))
        if not self.keyboardOpen:
            return False
        if event.keyCode in (0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C):
            return False
        # AltGr arrives as Ctrl+Alt; a printable result is typing, not a shortcut.
        if self.shortcut(event):
            if self.state.live:  # nothing is held back in continue mode
                self.drop_live()
                return False
            # Mid-composition, take the key so onKeyDown commits the wording. Left to TSF, the
            # composition was discarded (Ctrl+A lost the typed text).
            return bool(self.state.text)
        if event.keyCode == 0x76:  # F7 is the input method's while it is active
            return True
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
        self.setCompositionString(self.state.text)
        # TSF cursor offsets count UTF-16 code units.
        self.setCompositionCursor(len(self.state.text.encode("utf-16-le")) // 2)
        if self.state.question:
            candidates = [c.get("label", "") + (" - " + c["legend"] if c.get("legend") else "")
                          for c in self.state.question.get("choices") or []]
        else:
            candidates = (self.state.candidates if self.state.choosing else
                          [self.state.candidate] if self.state.candidate else [])
        self.setCandidateList(candidates)
        self.setShowCandidates(bool(candidates))

    def changed(self):
        if self.worker and (self.state.automatic or not self.state.text):
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=focused_app())
        self.publish()

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
                    self.showMessage("cd_AI: the request failed; Enter retries", 3)

    def onKeyDown(self, event):
        keylog("onKeyDown", hex(event.keyCode), "ctrl=%d" % event.isKeyDown(0x11), "len=%d" % len(self.state.text))
        self.poll_results()
        key = event.keyCode
        if self.shortcut(event):
            # Commit the wording and consume the key; pressing the shortcut again runs it. Passing
            # it on (not eaten after the test phase said eaten) made Edge drop the composition.
            self.setCommitString(self.state.commit())
            self.changed()
            return True
        if key == 0x0D:
            # Instruct holds the text until Enter sends it; the next Enter inserts the result.
            action = self.state.enter()
            if action == "submit":
                self.state.submit()
                if self.worker:
                    self.worker.schedule(self.state.revision, self.state.text, self.state.mode, immediate=True,
                                         app=focused_app(), look=self.state.look)
                self.showMessage("cd_AI: working… Enter inserts the result when ready", 3)
                self.publish()
                return True
            if action == "wait":
                self.showMessage("cd_AI: still working…", 2)
                return True
        if self.state.question and 0x31 <= key <= 0x39:  # an agent's question: the digit is the answer
            chosen = self.state.answer_choice(key - 0x30)
            if chosen and self.worker:
                self.worker.answer(*chosen)
                self.showMessage("cd_AI: " + self.state.status, 2)
            self.publish()
            return True
        if self.state.choosing and 0x31 <= key <= 0x39:  # 1-9 pick from the list, as in CJK input methods
            text = self.state.pick(key - 0x30)
            if text is not None:
                self.setCommitString(text)
                self.changed()
            return True
        if self.state.live and key not in (0x76, 0x77):  # F7 and F8 are handled below
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
        if key == 0x76:  # F7 switches mode: continue, instruct, rewrite.
            if self.state.mode == "rewrite" and self.state.text:
                self.setCommitString(self.state.text)  # continue types into the app: the held words go in
            self.state.next_mode()
            self.showMessage("cd_AI: " + self.state.mode, 2)
            self.changed()
            return True
        if key == 0x09 and not self.state.candidate:
            self.publish()
            return True
        if key in (0x09, 0x0D, 0x1B):
            # Enter reaches here in instruct mode only with a result ready (see above).
            self.setCommitString(self.state.commit(key == 0x09 or (key == 0x0D and self.state.mode == "instruct")))
        elif key == 0x08:
            self.state.backspace()
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
