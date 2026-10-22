"""InputMethodKit controller; all Cocoa client operations stay on the main thread."""
import objc
from AppKit import NSEventMaskKeyDown, NSEventTypeKeyDown
from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagControl
from Foundation import NSNotFound, NSTimer
from InputMethodKit import IMKInputController, IMKCandidates
from InputMethodKit import kIMKSingleColumnScrollingCandidatePanel, kIMKLocateCandidatesBelowHint

from claudish.composition import Composition
from claudish.client import Suggestions


class ClaudishInputController(IMKInputController):
    def initWithServer_delegate_client_(self, server, delegate, client):
        self = objc.super(ClaudishInputController, self).initWithServer_delegate_client_(
            server, delegate, client)
        if self is None:
            return None
        self.state = Composition()
        self.worker = None
        self.timer = None
        self.active = False
        self.panel = IMKCandidates.alloc().initWithServer_panelType_(
            server, kIMKSingleColumnScrollingCandidatePanel)
        return self

    def activateServer_(self, sender):
        self.active = True
        if self.worker is None:
            self.worker = Suggestions()
        if self.timer is None:
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.04, self, "pollSuggestions:", None, True)

    def deactivateServer_(self, sender):
        self.finish(self.client())
        self.stop()

    def inputControllerWillClose(self):
        self.stop()

    @objc.python_method
    def stop(self):
        self.active = False
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None
        if self.worker is not None:
            self.worker.close()
            self.worker = None
        self.state.change("")
        self.panel.hide()

    def recognizedEvents_(self, sender):
        return NSEventMaskKeyDown

    @objc.signature(b"v@:@")
    def pollSuggestions_(self, timer):
        if not self.active or self.worker is None:
            return
        result = self.worker.poll()
        if result:
            revision, data = result
            if "text" in data and self.state.offer(revision, data["text"], data.get("candidates", ())):
                self.panel.updateCandidates()
                self.panel.show(kIMKLocateCandidatesBelowHint)
            elif "error" in data:
                self.state.fail(revision)

    def candidates_(self, sender):
        if self.state.choosing:
            return list(self.state.candidates)
        return [self.state.candidate] if self.state.candidate else []

    def candidateSelected_(self, candidate):
        if not (self.active and self.state.candidate):
            return
        if self.state.choosing and str(candidate) in self.state.candidates:
            self.commit_pick(self.client(), self.state.candidates.index(str(candidate)) + 1)
        elif str(candidate) == self.state.candidate:
            self.finish(self.client(), suggested=True)

    @objc.python_method
    def commit_pick(self, client, number):
        """Insert the numbered candidate of an instruction's list (1-9 or a click in the panel)."""
        text = self.state.pick(number)
        if text is None:
            return
        if self.worker is not None:
            self.worker.schedule(self.state.revision, "")
        self.panel.hide()
        if client is not None:
            client.insertText_replacementRange_(text, (NSNotFound, 0))

    @objc.python_method
    def app(self, client):
        """The focused app's bundle identifier (for bindings), such as "com.apple.Terminal"."""
        try:
            return str(client.bundleIdentifier()) if client is not None else None
        except Exception:  # Not every client implements it.
            return None

    @objc.python_method
    def changed(self, client):
        if self.worker is not None and (self.state.automatic or not self.state.text):
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=self.app(client))
        self.panel.hide()
        # Cocoa ranges count UTF-16 code units, rather than Python code points.
        length = len(self.state.text.encode("utf-16-le")) // 2
        client.setMarkedText_selectionRange_replacementRange_(
            self.state.text, (length, 0), (NSNotFound, 0))

    @objc.python_method
    def finish(self, client, suggested=False):
        text = self.state.commit(suggested)
        if self.worker is not None:
            self.worker.schedule(self.state.revision, "")
        self.panel.hide()
        if text and client is not None:
            # Inserting replaces the client's existing marked text.
            client.insertText_replacementRange_(text, (NSNotFound, 0))

    def commitComposition_(self, sender):
        self.finish(self.client())

    def handleEvent_client_(self, event, client):
        if not self.active or event.type() != NSEventTypeKeyDown:
            return False
        flags = event.modifierFlags()
        # Option types characters such as — and €; it is not a shortcut by itself.
        if flags & (NSEventModifierFlagCommand | NSEventModifierFlagControl):
            self.finish(client)
            return False
        self.pollSuggestions_(None)
        key = event.keyCode()
        chars = event.characters() or ""
        if self.state.choosing and len(chars) == 1 and "1" <= chars <= "9":
            self.commit_pick(client, int(chars))
            return True
        if key == 100 and self.state.toggle_look():  # F8 in instruct: send a picture of this window too.
            self.changed(client)
            return True
        if key == 98 and self.state.text:  # F7 switches mode: rewrite, continue, instruct.
            self.state.next_mode()
            self.changed(client)
            return True
        if key == 97 and self.state.text:  # F6
            if self.state.candidate:
                self.panel.updateCandidates()
                self.panel.show(kIMKLocateCandidatesBelowHint)
            return True
        if key in (36, 76):  # Return, keypad Enter
            # Instruct holds the text until Enter sends it; the next Enter inserts the result.
            action = self.state.enter()
            if action == "submit":
                self.state.submit()
                if self.worker is not None:
                    self.worker.schedule(self.state.revision, self.state.text, self.state.mode, immediate=True,
                                         app=self.app(client), look=self.state.look)
            elif action in ("accept", "keep"):
                self.finish(client, suggested=action == "accept")
            return action != "pass"
        if key in (48, 53):  # Tab, Escape
            if not self.state.text:
                return False
            if key == 48 and not self.state.candidate:
                return True
            self.finish(client, suggested=key == 48)
            return True
        if key == 51:  # Backspace
            if not self.state.text:
                return False
            self.state.backspace()
            self.changed(client)
            return True
        text = event.characters() or ""
        # Navigation keys use private-use characters, which must not enter the draft.
        if key in (115, 116, 117, 119, 121, 123, 124, 125, 126) or not text or not text.isprintable():
            self.finish(client)
            return False
        for char in text:
            if not self.state.insert(char):
                self.finish(client)
                self.state.insert(char)
        self.changed(client)
        return True
