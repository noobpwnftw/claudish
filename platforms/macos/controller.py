"""InputMethodKit controller; all Cocoa client operations stay on the main thread."""
import os
import time
import traceback

import objc
from AppKit import NSEventMaskFlagsChanged, NSEventMaskKeyDown, NSEventTypeFlagsChanged, NSEventTypeKeyDown
from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagControl, NSEventModifierFlagShift
from AppKit import NSAttributedString, NSColor, NSForegroundColorAttributeName
from Foundation import NSNotFound, NSTimer
from InputMethodKit import IMKInputController, kIMKLocateCandidatesBelowHint

from claudish.composition import MAX_COMPOSITION, Composition, ShiftTap
from claudish.client import Suggestions
from claudish.screen import is_terminal
from panel import Overlay, Panel  # cd_AI's own panel and suggestion overlay (G45)

# A file path: event kinds and errors, never typed text. An input method started by macOS (or with
# open -g) does not see launchctl setenv, so an existing ~/Library/Logs/cd_AI-trace.log turns it on too.
TRACE = os.environ.get("CLAUDISH_TRACE") or next(
    (path for path in [os.path.expanduser("~/Library/Logs/cd_AI-trace.log")] if os.path.exists(path)), None)


def trace(*fields):
    if TRACE:
        with open(TRACE, "a") as out:
            out.write("%.3f %s\n" % (time.time(), " ".join(str(f) for f in fields)))


SURROUNDING = 8000
# One candidate panel for the server, as in Apple's sample: a panel per controller registers with
# the server and is freed with its controller, and IMK later messaged the freed panel while
# deactivating (a crash on macOS 26).
PANEL = OVERLAY = None  # one panel and one overlay for the server, shared by its controllers


def unpack(rect):
    """((x, y), (w, h)) from an NSRect or a nested tuple."""
    origin, size = (rect.origin, rect.size) if hasattr(rect, "origin") else rect
    x, y = (origin.x, origin.y) if hasattr(origin, "x") else origin
    w, h = (size.width, size.height) if hasattr(size, "width") else size
    return (x, y), (w, h)


# IMK's attributesForCharacterIndex:lineHeightRectangle: hands the rectangle back through a pointer;
# PyObjC needs to be told, or it passes NULL and only the attributes come back.
objc.registerMetaDataForSelector(b"NSObject", b"attributesForCharacterIndex:lineHeightRectangle:",
                                 {"arguments": {3: {"type_modifier": objc._C_OUT}}})


class Shown:
    """The panel as the controller's call sites use it (they were written for IMKCandidates): show
    and update draw cd_AI's own panel from the state; hide hides it."""

    def __init__(self, controller):
        self.controller = controller

    def show_(self, where=None):
        self.controller.show_panel()

    def updateCandidates(self):
        pass

    def hide(self):
        PANEL.hide()


class ClaudishInputController(IMKInputController):
    def initWithServer_delegate_client_(self, server, delegate, client):
        self = objc.super(ClaudishInputController, self).initWithServer_delegate_client_(
            server, delegate, client)
        if self is None:
            return None
        self.state = Composition()
        self.shift = ShiftTap()  # Shift alone, tapped: the mode switch
        self.worker = None
        self.timer = None
        self.active = False
        global PANEL, OVERLAY
        if PANEL is None:
            PANEL, OVERLAY = Panel(), Overlay()
        self.panel = Shown(self)
        return self

    def activateServer_(self, sender):
        objc.super(ClaudishInputController, self).activateServer_(sender)
        self.active = True
        if self.worker is None:
            self.worker = Suggestions()
        if self.timer is None:
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.04, self, "pollSuggestions:", None, True)

    def deactivateServer_(self, sender):
        try:
            self.finish(self.client())
            self.stop()
        except Exception:
            trace("deactivate failed", traceback.format_exc())
        objc.super(ClaudishInputController, self).deactivateServer_(sender)

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
        OVERLAY.hide()

    def recognizedEvents_(self, sender):
        return NSEventMaskKeyDown | NSEventMaskFlagsChanged  # flags: a Shift tap switches mode

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
                if self.state.converted:  # the rewrite you asked for with Tab, in place of your words
                    client = self.client()
                    if client is not None:
                        self.changed(client)
                    return
                if self.state.live:  # continue: the rest of the sentence, in grey after the caret
                    client = self.client()
                    if client is not None:
                        self.show_ghost(client)
                    return
                if self.state.choosing:  # an instruction's drafts; rewrite converts in place on Tab
                    self.panel.updateCandidates()
                    self.panel.show_(kIMKLocateCandidatesBelowHint)
            elif "question" in data and self.state.ask(revision, data["question"], data["session"]):
                self.panel.updateCandidates()  # the choices, numbered by the panel
                self.panel.show_(kIMKLocateCandidatesBelowHint)
            elif "progress" in data or "partial" in data:
                self.state.note(revision, data.get("progress") or data.get("partial"))
            elif "done" in data and self.state.done(revision):
                self.panel.hide()  # a helper took the task: nothing to insert
                client = self.client()
                if client is not None:
                    client.setMarkedText_selectionRange_replacementRange_("", (0, 0), (NSNotFound, 0))
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
    def caret(self, client):
        """The caret's line in screen coordinates ((x, y), (w, h)), y at the line's bottom, for the
        panel and the overlay. IMK's lineHeightRectangle is what input methods place windows by;
        firstRectForCharacterRange came back with y at the line's top in our tests, so it is the
        fallback, corrected for that."""
        try:
            selected = client.selectedRange()
            location = selected.location if hasattr(selected, "location") else selected[0]
        except Exception:
            location = 0
        try:
            found = client.attributesForCharacterIndex_lineHeightRectangle_(location, None)
            rect = found[1] if isinstance(found, tuple) and len(found) == 2 else None
            if rect is not None:
                (x, y), (w, h) = unpack(rect)
                if h > 0:
                    trace("caret line", round(x), round(y), round(w), round(h), "at", location)
                    return (x, y), (w, h)
        except Exception:
            trace("caret line failed", traceback.format_exc().splitlines()[-1])
        try:
            found = client.firstRectForCharacterRange_actualRange_((location, 0), None)
            rect = found[0] if isinstance(found, tuple) and len(found) == 2 and not hasattr(found, "origin") else found
            (x, y), (w, h) = unpack(rect)
            if h > 0:
                trace("caret first", round(x), round(y), round(w), round(h), "at", location)
                return (x, y - h), (w, h)
        except Exception:
            trace("caret failed", traceback.format_exc().splitlines()[-1])
        return (200, 400), (0, 18)

    @objc.python_method
    def font(self, client):
        """The app's font just before the caret (from its own text), so the suggestion reads as the
        same text; None when the app does not say."""
        try:
            selected = client.selectedRange()
            location = selected.location if hasattr(selected, "location") else selected[0]
            if location < 1:
                return None
            found = client.attributedSubstringFromRange_((location - 1, 1))
            return found.attribute_atIndex_effectiveRange_("NSFont", 0, None)[0] if found is not None else None
        except Exception:
            trace("font failed", traceback.format_exc().splitlines()[-1])
            return None

    @objc.python_method
    def show_ghost(self, client):
        """Continue's suggestion: grey, after the caret, never looking typed. Drawn by our overlay
        when nothing follows on the line (IMK drops marked text's colour); with text after the caret
        an overlay would cover it, so there it stays marked text."""
        ghost = self.state.ghost
        after = self.around_caret(client)[1] if ghost else ""
        if ghost and not after.split("\n", 1)[0].strip():
            client.setMarkedText_selectionRange_replacementRange_("", (0, 0), (NSNotFound, 0))
            OVERLAY.show(self.caret(client), ghost, self.font(client))
            trace("ghost overlay", len(ghost))
            return
        OVERLAY.hide()
        client.setMarkedText_selectionRange_replacementRange_(self.grey(ghost), (0, 0), (NSNotFound, 0))

    @objc.python_method
    def show_panel(self, client=None):
        """The panel at the caret: a question with its choices, an instruction's drafts, or the one
        short hint while composing (docs/design/visual.md); nothing in continue."""
        state = self.state
        client = client if client is not None else self.client()
        if state.live or not state.text or client is None:
            PANEL.hide()
            return
        rect = self.caret(client)
        if state.question and not state.reply:
            choices = state.question.get("choices") or []
            PANEL.show(rect, title=state.question.get("text", ""),
                       items=[c.get("label", "") + (" — " + c["legend"] if c.get("legend") else "") for c in choices],
                       selected=0 if state.asks else -1,  # an approval highlights nothing: only a number answers it
                       hint=("Enter: the first · 1–%d · or type a reply" if state.asks else "1–%d · or type a reply")
                       % len(choices))
        elif state.choosing:
            PANEL.show(rect, items=list(state.candidates), hint=state.hint())
        elif state.hint():
            PANEL.show(rect, hint=state.hint())
        else:
            PANEL.hide()

    @objc.python_method
    def grey(self, text):
        """Continue's suggestion as marked text in the secondary label color, so it reads as an
        offer rather than typed text (apps that draw marked text their own way may ignore it)."""
        if not text:
            return text
        return NSAttributedString.alloc().initWithString_attributes_(
            text, {NSForegroundColorAttributeName: NSColor.secondaryLabelColor()})

    @objc.python_method
    def switch_mode(self, client):
        """A Shift tap: continue <-> compose. Leaving compose keeps what you see, as typed. (One
        input source: macOS did not present input modes of an unsigned bundle as modes, so the mode
        is cd_AI's own, shown by cd_AI.)"""
        kept = self.state.toggle()
        if self.worker is not None:
            self.worker.schedule(self.state.revision, "")  # what was asked belongs to the old mode
        if kept:
            client.insertText_replacementRange_(kept, (NSNotFound, 0))
        self.changed(client)

    @objc.python_method
    def take_selection(self, client):
        """Rewrite with nothing composed: the app's selection becomes the composition (CJK input
        methods call it reconversion), replaced by marked text until you keep the rewrite or your
        words."""
        try:
            selected = client.selectedRange()
            location, length = (selected.location, selected.length) if hasattr(selected, "location") else selected
            if location == NSNotFound or not 0 < length <= MAX_COMPOSITION:
                return False
            found = client.attributedSubstringFromRange_((location, length))
            text = str(found.string()) if found is not None else ""
        except Exception:
            return False
        if not text:
            return False
        self.state.adopt(text)
        units = len(text.encode("utf-16-le")) // 2
        client.setMarkedText_selectionRange_replacementRange_(text, (units, 0), (location, length))
        return True

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
        self.state.quiet = is_terminal(self.app(client))  # a terminal's command line is not prose
        after = self.around_caret(client)[1] if self.state.live else ""
        self.state.inside = bool(after.split("\n", 1)[0].strip())  # continue waits for a line's end
        trace("changed", self.state.mode, "asks" if self.state.automatic else "waits")
        if self.worker is not None and self.state.automatic:  # continue: what follows the caret too
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=self.app(client),
                                 after=after[:500])
        elif self.worker is not None and not self.state.text:
            self.worker.schedule(self.state.revision, "")
        if self.state.live:  # the only thing shown is the suggestion, with the caret before it
            self.panel.hide()
            self.show_ghost(client)
            return
        OVERLAY.hide()
        shown = self.state.shown  # rewrite after Tab: the rewrite, in place of your words
        # Cocoa ranges count UTF-16 code units, rather than Python code points.
        length = len(shown.encode("utf-16-le")) // 2
        client.setMarkedText_selectionRange_replacementRange_(shown, (length, 0), (NSNotFound, 0))
        self.show_panel(client)  # what is waiting (drafts, a question) or the one short hint

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
            OVERLAY.hide()
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
            special = {36: "Return", 48: "Tab", 51: "Backspace", 53: "Escape", 56: "Shift", 60: "Shift", 97: "F6", 100: "F8"}
            trace("key", special.get(event.keyCode(), "char"), self.state.mode, "handled" if handled else "passed")
            return handled
        except Exception:
            trace("key failed", traceback.format_exc())
            raise

    @objc.python_method
    def handle(self, event, client):
        if self.active and event.type() == NSEventTypeFlagsChanged:
            if event.keyCode() in (56, 60):  # left or right Shift, pressed or released
                if event.modifierFlags() & NSEventModifierFlagShift:
                    self.shift.press(time.monotonic())
                elif self.shift.release(time.monotonic()):
                    self.switch_mode(client)
            else:
                self.shift.other()
            return False  # the app still sees its modifiers
        if not self.active or event.type() != NSEventTypeKeyDown:
            return False
        self.shift.other()
        flags = event.modifierFlags()
        # Option types characters such as — and €; it is not a shortcut by itself.
        if flags & (NSEventModifierFlagCommand | NSEventModifierFlagControl):
            self.finish(client)
            return False
        self.pollSuggestions_(None)
        key = event.keyCode()
        chars = event.characters() or ""
        if self.state.question and not self.state.reply and len(chars) == 1 and "1" <= chars <= "9":  # the answer to the agent
            chosen = self.state.answer_choice(int(chars))
            if chosen and self.worker is not None:
                self.worker.answer(*chosen)
                self.panel.hide()
            return True
        if self.state.choosing and not self.state.question and len(chars) == 1 and "1" <= chars <= "9":
            self.commit_pick(client, int(chars))
            return True
        if key == 100 and self.state.toggle_look():  # F8 in instruct: send a picture of this window too.
            self.changed(client)
            return True
        if self.state.live:
            return self.live_key(client, key, chars)
        if key == 97 and self.state.text:  # F6
            if self.state.choosing:
                self.panel.updateCandidates()
                self.panel.show_(kIMKLocateCandidatesBelowHint)
            return True
        if key in (36, 76) and flags & NSEventModifierFlagShift and self.state.text:
            kept = self.state.keep()  # Shift+Enter: as it is, and keep composing
            self.changed(client)
            client.insertText_replacementRange_(kept, (NSNotFound, 0))
            return True
        if key in (36, 76):  # Return, keypad Enter
            # Instruct holds the text until Enter sends it; the next Enter inserts the result.
            action = self.state.enter()
            if action == "choose":  # the first choice of a question that is not an approval
                chosen = self.state.answer_choice(1)
                if chosen and self.worker is not None:
                    self.worker.answer(*chosen)
                self.panel.hide()
                self.changed(client)
                return True
            if action == "reply":  # your own words, in answer to the agent's question
                session, question, words = self.state.answer_text()
                if self.worker is not None:
                    self.worker.answer(session, question, text=words)
                self.panel.hide()
                self.changed(client)
                return True
            if action == "submit":
                self.state.submit()
                if self.worker is not None:
                    before, after = self.around_caret(client)  # the text box, for this turn of its conversation
                    self.worker.schedule(self.state.revision, self.state.text, "instruct", immediate=True,
                                         app=self.app(client), look=self.state.look, before=before, after=after)
            elif action in ("accept", "keep"):
                self.finish(client, suggested=action == "accept")
            return action != "pass"
        if key == 48:  # Tab
            if not self.state.live and not self.state.text:
                self.take_selection(client)  # a selection: rewrite it in place
            action = self.state.tab()
            if action == "choose":
                chosen = self.state.answer_choice(1)
                if chosen and self.worker is not None:
                    self.worker.answer(*chosen)
                self.panel.hide()
                self.changed(client)
                return True
            if action == "accept":
                self.finish(client, suggested=True)
            elif action == "request":  # rewrite: ask now; it converts in place when it arrives
                if self.worker is not None:
                    before, after = self.around_caret(client)  # where the rewrite goes
                    self.worker.schedule(self.state.revision, self.state.text, "rewrite", immediate=True,
                                         app=self.app(client), before=before[-1500:], after=after[:500])
            elif action == "convert":
                self.changed(client)
            return action != "pass"
        if key == 53:  # Escape: one step back
            action = self.state.escape()
            if action == "clear":  # the reply goes; the question stays
                self.changed(client)
            elif action == "keep":
                self.finish(client)
            elif action in ("back", "drop"):
                if self.worker is not None:
                    self.worker.schedule(self.state.revision, "")  # stop a pending answer
                self.changed(client)
            return action != "pass"
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
        if all(self.state.passes(char) for char in text):  # nothing composed: the space is the app's text
            client.insertText_replacementRange_(text, (NSNotFound, 0))
            return True
        for char in text:
            if not self.state.insert(char):
                self.finish(client)
                self.state.insert(char)
        self.changed(client)
        return True
