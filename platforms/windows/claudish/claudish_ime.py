"""PIME/TSF adapter. Shared files are copied here by install.ps1."""
from textService import TextService
from .composition import Composition
from .client import Suggestions


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
        if not self.keyboardOpen:
            return False
        if event.keyCode in (0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C):
            return False
        # Preserve Ctrl/Alt/Win shortcuts. TSF owns external composition termination.
        # AltGr arrives as Ctrl+Alt; a printable result is typing, not a shortcut.
        altgr = (event.isKeyDown(0x11) and event.isKeyDown(0x12) and event.isPrintableChar()
                 and not (event.isKeyDown(0x5B) or event.isKeyDown(0x5C)))
        if not altgr and any(event.isKeyDown(key) for key in (0x11, 0x12, 0x5B, 0x5C)):
            return False
        return event.isPrintableChar() or bool(self.state.text)

    def publish(self):
        self.setCompositionString(self.state.text)
        # TSF cursor offsets count UTF-16 code units.
        self.setCompositionCursor(len(self.state.text.encode("utf-16-le")) // 2)
        candidate = self.state.candidate
        self.setCandidateList([candidate] if candidate else [])
        self.setShowCandidates(bool(candidate))

    def changed(self):
        if self.worker and (self.state.automatic or not self.state.text):
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=focused_app())
        self.publish()

    def onKeyDown(self, event):
        # PIME replies are event-driven: poll on a key event, never mutate TSF off-thread.
        result = self.worker.poll() if self.worker else None
        if result:
            revision, data = result
            if "text" in data:
                self.state.offer(revision, data["text"])
            elif "error" in data:
                self.state.fail(revision)
                if self.state.failed:
                    self.showMessage("cd_AI: the request failed; Enter retries", 3)
        key = event.keyCode
        if key == 0x0D:
            # Instruct holds the text until Enter sends it; the next Enter inserts the result.
            action = self.state.enter()
            if action == "submit":
                self.state.submit()
                if self.worker:
                    self.worker.schedule(self.state.revision, self.state.text, self.state.mode, immediate=True,
                                         app=focused_app())
                self.showMessage("cd_AI: working… Enter inserts the result when ready", 3)
                self.publish()
                return True
            if action == "wait":
                self.showMessage("cd_AI: still working…", 2)
                return True
        if key == 0x75:  # F6 previews the ready candidate without committing it.
            self.publish()
            return True
        if key == 0x76:  # F7 switches mode: rewrite, continue, instruct.
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

    def onCompositionTerminated(self, forced):
        super().onCompositionTerminated(forced)
        self.state.change("")
        if self.worker:
            self.worker.schedule(self.state.revision, "")

    def onKeyboardStatusChanged(self, opened):
        super().onKeyboardStatusChanged(opened)
        self.keyboardOpen = opened
        if not opened:
            self.state.change("")
            self.changed()
