"""InputMethodKit controller; all Cocoa client operations stay on the main thread."""
import os
import time
import traceback

import objc
from AppKit import NSEventMaskKeyDown, NSEventTypeKeyDown
from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagControl
from AppKit import NSAttributedString, NSColor, NSForegroundColorAttributeName
from Foundation import NSNotFound, NSTimer
from InputMethodKit import IMKInputController, IMKCandidates
from InputMethodKit import kIMKSingleColumnScrollingCandidatePanel, kIMKLocateCandidatesBelowHint

from claudish.composition import MAX_COMPOSITION, Composition
from claudish.client import Suggestions

TRACE = os.environ.get("CLAUDISH_TRACE")  # a file path: event kinds and errors, never typed text


def trace(*fields):
    if TRACE:
        with open(TRACE, "a") as out:
            out.write("%.3f %s\n" % (time.time(), " ".join(str(f) for f in fields)))


SURROUNDING = 8000  # characters each side of the caret an instruction takes along (as on Linux)


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
        try:
            self.poll()
        except Exception:  # an error here would vanish into the host app's run loop
            trace("poll failed", traceback.format_exc())
            raise

    @objc.python_method
    def poll(self):
        if not self.active or self.worker is None:
            return
        result = self.worker.poll()
        if result:
            trace("result", sorted(result[1]), "current" if result[0] == self.state.revision else "stale")
        if result:
            revision, data = result
            if "text" in data and self.state.offer(revision, data["text"], data.get("candidates", ())):
                if self.state.live:  # continue: the rest of the sentence, as marked text after the caret
                    client = self.client()
                    if client is not None:
                        client.setMarkedText_selectionRange_replacementRange_(self.grey(self.state.ghost),
                                                                              (0, 0), (NSNotFound, 0))
                    return
                self.panel.updateCandidates()
                self.panel.show(kIMKLocateCandidatesBelowHint)
            elif "question" in data and self.state.ask(revision, data["question"], data["session"]):
                self.panel.updateCandidates()  # the choices, numbered by the panel
                self.panel.show(kIMKLocateCandidatesBelowHint)
            elif "progress" in data or "partial" in data:
                self.state.note(revision, data.get("progress") or data.get("partial"))
            elif "error" in data:
                self.state.fail(revision)

    def candidates_(self, sender):
        if self.state.question:
            return [c.get("label", "") + (" — " + c["legend"] if c.get("legend") else "")
                    for c in self.state.question.get("choices") or []]
        if self.state.choosing:
            return list(self.state.candidates)
        return [self.state.candidate] if self.state.candidate else []

    def candidateSelected_(self, candidate):
        if self.active and self.state.question:  # a click on one of the agent's choices
            lines = self.candidates_(None)
            if str(candidate) in lines:
                chosen = self.state.answer_choice(lines.index(str(candidate)) + 1)
                if chosen and self.worker is not None:
                    self.worker.answer(*chosen)
                    self.panel.hide()
            return
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
    def grey(self, text):
        """Continue's suggestion as marked text in the secondary label color, so it reads as an
        offer rather than typed text (apps that draw marked text their own way may ignore it)."""
        if not text:
            return text
        return NSAttributedString.alloc().initWithString_attributes_(
            text, {NSForegroundColorAttributeName: NSColor.secondaryLabelColor()})

    @objc.python_method
    def around_caret(self, client):
        """(before, after): the client's text around the caret (IMKTextInput), or empty when it does
        not share it. Chromium-based apps (VS Code, browsers) answer only about 100 characters
        around the selection; native text views answer the whole text."""
        def text(location, length):
            if length <= 0:
                return ""
            # Not stringFromRange:actualRange:: PyObjC passes its out-parameter as NULL, and IMK's
            # client wrapper writes to it anyway (a crash on macOS 26, found in a real session).
            found = client.attributedSubstringFromRange_((location, length))
            return str(found.string()) if found is not None else ""
        def pair(found):
            return (found.location, found.length) if hasattr(found, "location") else tuple(found)
        try:
            location, length = pair(client.selectedRange())
            marked = pair(client.markedRange())  # our own composition or suggestion is not the app's text
            if marked[0] != NSNotFound and marked[1]:
                location, length = marked
            total = client.length()
            if location == NSNotFound or location > total:
                return "", ""
            start = max(0, location - SURROUNDING)
            end = min(total, location + length)
            return text(start, location - start), text(end, min(SURROUNDING, total - end))
        except Exception:  # not every client implements these
            return "", ""

    @objc.python_method
    def changed(self, client):
        trace("changed", self.state.mode, "asks" if self.state.automatic else "waits")
        if self.worker is not None and (self.state.automatic or not self.state.text):
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=self.app(client))
        self.panel.hide()
        if self.state.live:  # the only marked text is the suggestion, with the caret before it
            client.setMarkedText_selectionRange_replacementRange_(self.grey(self.state.ghost), (0, 0),
                                                                  (NSNotFound, 0))
            return
        # Cocoa ranges count UTF-16 code units, rather than Python code points.
        length = len(self.state.text.encode("utf-16-le")) // 2
        client.setMarkedText_selectionRange_replacementRange_(
            self.state.text, (length, 0), (NSNotFound, 0))

    @objc.python_method
    def live_key(self, client, key, chars):
        """Continue mode: keys go to the app as typed; Tab takes the suggestion, Esc dismisses it."""
        state = self.state
        if key == 48:  # Tab
            ghost = state.take_ghost()
            if not ghost:
                return False  # no suggestion: Tab is the app's
            client.insertText_replacementRange_(ghost, (NSNotFound, 0))
            self.changed(client)
            return True
        if key == 53:  # Escape
            if not state.ghost:
                return False
            state.dismiss()
            self.changed(client)
            return True
        navigation = key in (36, 76, 51, 115, 116, 117, 119, 121, 123, 124, 125, 126)
        if navigation or not chars or not chars.isprintable():
            if key == 51 and state.text:
                state.backspace()
            else:
                state.change("")  # Enter, arrows, anything else: the context starts over
            self.changed(client)  # clears the suggestion before the app handles the key
            return False
        if not state.text:  # a fresh start (a click, a paste, a new field): begin from the app's text
            state.change(self.around_caret(client)[0][-MAX_COMPOSITION:])
        for char in chars:
            client.insertText_replacementRange_(state.type_live(char), (NSNotFound, 0))
        self.changed(client)
        return True

    @objc.python_method
    def finish(self, client, suggested=False):
        if self.state.live:  # nothing is held back in continue mode: drop the suggestion, start over
            self.state.change("")
            if self.worker is not None:
                self.worker.schedule(self.state.revision, "")
            self.panel.hide()
            if client is not None:
                client.setMarkedText_selectionRange_replacementRange_("", (0, 0), (NSNotFound, 0))
            return
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
        try:
            handled = self.handle(event, client)
            special = {36: "Return", 48: "Tab", 51: "Backspace", 53: "Escape", 97: "F6", 98: "F7", 100: "F8"}
            trace("key", special.get(event.keyCode(), "char"), self.state.mode, "handled" if handled else "passed")
            return handled
        except Exception:
            trace("key failed", traceback.format_exc())
            raise

    @objc.python_method
    def handle(self, event, client):
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
        if self.state.question and len(chars) == 1 and "1" <= chars <= "9":  # the answer to the agent
            chosen = self.state.answer_choice(int(chars))
            if chosen and self.worker is not None:
                self.worker.answer(*chosen)
                self.panel.hide()
            return True
        if self.state.choosing and len(chars) == 1 and "1" <= chars <= "9":
            self.commit_pick(client, int(chars))
            return True
        if key == 100 and self.state.toggle_look():  # F8 in instruct: send a picture of this window too.
            self.changed(client)
            return True
        if key == 98:  # F7 switches mode: continue, instruct, rewrite (the input method's key while active).
            entering_live = self.state.mode == "rewrite" and self.state.text
            self.state.next_mode()
            if entering_live:  # continue types into the app: the held words go in, and stay as context
                client.insertText_replacementRange_(self.state.text, (NSNotFound, 0))
            self.changed(client)
            return True
        if self.state.live:
            return self.live_key(client, key, chars)
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
                    before, after = self.around_caret(client)  # the text box, for this turn of its conversation
                    self.worker.schedule(self.state.revision, self.state.text, self.state.mode, immediate=True,
                                         app=self.app(client), look=self.state.look, before=before, after=after)
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
