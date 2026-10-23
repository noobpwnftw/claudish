"""InputMethodKit controller; all Cocoa client operations stay on the main thread."""
import os
import time
import traceback

import objc
from AppKit import NSEventMaskFlagsChanged, NSEventMaskKeyDown, NSEventTypeFlagsChanged, NSEventTypeKeyDown
from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagControl, NSEventModifierFlagShift
from Foundation import NSNotFound, NSTimer
from InputMethodKit import IMKInputController

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
PANEL = OVERLAY = TOAST = None  # one panel, overlay and toast for the server, shared by its controllers


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
        global PANEL, OVERLAY, TOAST
        if PANEL is None:
            PANEL, OVERLAY, TOAST = Panel(), Overlay(), Panel()
        self.drawn = None  # the panel as last drawn (Composition.panel()), redrawn when it changes
        return self

    def activateServer_(self, sender):
        objc.super(ClaudishInputController, self).activateServer_(sender)
        self.active = True
        if self.worker is None:
            self.worker = Suggestions()
        if self.timer is None:
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.04, self, "pollSuggestions:", None, True)
        pill = self.state.returned(self.app(self.client()))  # back where an exchange was held
        if pill:
            self.show_toast(pill)

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
        self.hide_panel()
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
            if "text" in data and self.state.offer(revision, data["text"], data.get("candidates", ()),
                                                   data.get("hosted", "")):
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
            elif "question" in data:
                self.state.ask(revision, data["question"], data["session"])
            elif "progress" in data or "partial" in data:
                self.state.note(revision, data.get("progress") or data.get("partial"))
            elif "done" in data and self.state.done(revision):
                client = self.client()  # a helper took the task: nothing to insert
                if client is not None:
                    client.setMarkedText_selectionRange_replacementRange_("", (0, 0), (NSNotFound, 0))
            elif "error" in data:
                self.state.fail(revision, data["error"])
        if self.state.panel() != self.drawn:  # an answer, a question, progress, or the pause for the keys
            self.show_panel()

    @objc.python_method
    def pick(self, number):
        """A click on a row of the panel: the same as its number key."""
        if not self.active:
            return
        if self.state.question and not self.state.reply:
            chosen = self.state.answer_choice(number)
            if chosen and self.worker is not None:
                self.worker.answer(*chosen)
            self.show_panel()
        elif self.state.choosing or self.state.candidate:
            self.commit_pick(self.client(), number)

    @objc.python_method
    def commit_pick(self, client, number):
        """Insert the numbered candidate of an instruction's list (1-9 or a click in the panel)."""
        text = self.state.pick(number)
        if text is None:
            return
        if self.worker is not None:
            self.worker.schedule(self.state.revision, "")
        self.hide_panel()
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
    def show_ghost(self, client):
        """Continue's suggestion: cd_AI's own grey text right after the caret (docs/design/visual.md).
        Continue asks only at the end of a line (inside), so it never covers the app's text."""
        ghost = self.state.ghost
        if not ghost or self.state.inside:  # text after the caret on its line: nothing to cover it with
            OVERLAY.hide()
            return
        OVERLAY.show(self.caret(client), ghost)
        trace("ghost overlay", len(ghost))

    @objc.python_method
    def show_panel(self, client=None):
        """The panel at the caret, as Composition.panel() describes it; nothing in continue."""
        spec = self.state.panel()
        client = client if client is not None else self.client()
        if not spec or client is None:
            self.hide_panel()
            return
        TOAST.hide()  # a panel replaces a toast at the caret
        PANEL.show(self.caret(client), spec, self.pick)
        self.drawn = spec

    @objc.python_method
    def show_toast(self, spec, client=None):
        """A panel shown briefly at the caret: the mode switch, or what Esc just dropped."""
        client = client if client is not None else self.client()
        if client is None:
            return
        TOAST.show(self.caret(client), spec)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(2.0, self, "hideToast:", None, False)

    @objc.signature(b"v@:@")
    def hideToast_(self, timer):
        TOAST.hide()

    @objc.python_method
    def hide_panel(self):
        PANEL.hide()
        self.drawn = None

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
        self.show_toast(self.state.toast(), client)

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
            self.hide_panel()
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
            self.hide_panel()
            OVERLAY.hide()
            if client is not None:
                client.setMarkedText_selectionRange_replacementRange_("", (0, 0), (NSNotFound, 0))
            return
        if self.state.sent and not suggested:
            # The app ends the composition (a click, a focus change): an instruction's exchange is
            # held for this app, its work going on; a reply you were typing is never inserted.
            self.state.leave(self.app(client))
            self.hide_panel()
            if client is not None:
                client.setMarkedText_selectionRange_replacementRange_("", (0, 0), (NSNotFound, 0))
            return
        # Your own words, never the model's unless you asked for them (a rewrite waits for Tab).
        text = self.state.commit(suggested)
        if self.worker is not None:
            self.worker.schedule(self.state.revision, "")
        self.hide_panel()
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
        # Choices are not numbered: digits are text in English, as Space is (↑/↓ and Enter choose).
        if key == 100 and self.state.toggle_look():  # F8 in instruct: send a picture of this window too.
            self.changed(client)
            return True
        if self.state.live:
            return self.live_key(client, key, chars)
        if key in (36, 76) and flags & NSEventModifierFlagShift and self.state.text:
            kept = self.state.keep()  # Shift+Enter: as it is, and keep composing
            self.changed(client)
            client.insertText_replacementRange_(kept, (NSNotFound, 0))
            return True
        if key in (36, 76):  # Return, keypad Enter
            # Instruct holds the text until Enter sends it; the next Enter inserts the result.
            action = self.state.enter()
            if action == "choose":  # the first choice of a question that is not an approval
                chosen = self.state.answer_choice(self.state.chosen)
                if chosen and self.worker is not None:
                    self.worker.answer(*chosen)
                self.changed(client)
                return True
            if action == "reply":  # your own words, in answer to the agent's question
                session, question, words = self.state.answer_text()
                if self.worker is not None:
                    self.worker.answer(session, question, text=words)
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
                chosen = self.state.answer_choice(self.state.chosen)
                if chosen and self.worker is not None:
                    self.worker.answer(*chosen)
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
        if key in (126, 125) and self.state.move(-1 if key == 126 else 1):  # ↑ and ↓ move the highlight
            self.show_panel(client)
            return True
        if key == 53 and flags & NSEventModifierFlagShift and self.state.restore():  # Shift+Esc: the dropped one, back
            if self.state.working and self.worker is not None:  # held while it worked: ask again
                self.worker.schedule(self.state.revision, self.state.text, "instruct", immediate=True,
                                     app=self.app(client))
            self.changed(client)
            return True
        if key == 53:  # Escape: one step back
            action = self.state.escape()
            if action in ("clear", "drop"):  # words discarded: said, with the key that brings them back
                self.show_toast(self.state.dropped_toast(), client)
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
