"""InputMethodKit controller; all Cocoa client operations stay on the main thread."""
import ctypes
import os
import time
import traceback

import objc
from AppKit import NSEventMaskFlagsChanged, NSEventMaskKeyDown, NSEventTypeFlagsChanged, NSEventTypeKeyDown
from AppKit import NSAttributedString, NSColor, NSEvent, NSEventModifierFlagCommand, NSEventModifierFlagControl, NSEventModifierFlagOption, NSEventModifierFlagShift
from Foundation import NSNotFound, NSTimer
from InputMethodKit import IMKInputController

from claudish.composition import ACCENTS, AROUND, MAX_COMPOSITION, Composition, ShiftTap, accented, typeable, window
from claudish.client import Suggestions
from claudish.screen import is_terminal
from panel import Overlay, Panel, units  # cd_AI's own panel and suggestion overlay (G45)
from layout import layout  # the keyboard layout's own dead keys

# A file path: event kinds and errors, never typed text. An input method started by macOS (or with
# open -g) does not see launchctl setenv, so an existing ~/Library/Logs/cd_AI-trace.log turns it on too.
TRACE = os.environ.get("CLAUDISH_TRACE") or next(
    (path for path in [os.path.expanduser("~/Library/Logs/cd_AI-trace.log")] if os.path.exists(path)), None)


def trace(*fields):
    if TRACE:
        with open(TRACE, "a", encoding="utf-8") as out:
            out.write("%.3f %s\n" % (time.time(), " ".join(str(f) for f in fields)))


def secure_input():
    """Whether a password field (or Terminal's Secure Keyboard Entry) has secure input on: then
    keys go straight to it, and nothing is composed, shown, or sent to a model."""
    if not SECURE:  # read once: it is asked at every key and poll
        try:
            carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
            carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool
            SECURE.append(carbon.IsSecureEventInputEnabled)
        except (OSError, AttributeError):
            SECURE.append(None)
    return bool(SECURE[0]()) if SECURE[0] else False


SECURE = []


# Each mode is an input mode of cd_AI's input source (Info.plist: "Claudish — Compose", "Claudish —
# Continue", named as Apple's "Pinyin – Simplified", with an em dash), its icon in the menu bar: "AI"
# for compose, "cd" for continue, as Mozc and AquaSKK show theirs.
MODE_IDS = {"compose": "org.claudish.inputmethod.Claudish.English",
            "continue": "org.claudish.inputmethod.Claudish.Continue"}
INPUT_MODE_TAG = int.from_bytes(b"imim", "big")  # kTSMDocumentInputModePropertyTag
MODE_TOAST = False  # macOS says the new input mode at the caret itself; cd_AI's toast is kept, off (owner)
# One candidate panel for the server, as in Apple's sample: a panel per controller registers with
# the server and is freed with its controller, and IMK later messaged the freed panel while
# deactivating (a crash on macOS 26).
PANEL = OVERLAY = TOAST = None  # one panel, overlay and toast for the server, shared by its controllers
OWNER = [None]  # the controller last activated: only it hides them (another's late deactivate or close must not)
TOAST_TIMER = [None]  # the shared toast's hide timer: another text box's toast (or pill) replaces it


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


def span(found):
    """An NSRange as (location, length): PyObjC gives a struct or a tuple."""
    return (found.location, found.length) if hasattr(found, "location") else tuple(found)


def substring(client, location, length):
    """The client's text in a range. Not stringFromRange:actualRange:: PyObjC passes its
    out-parameter as NULL, and IMK's client wrapper writes to it anyway (a crash on macOS 26)."""
    found = client.attributedSubstringFromRange_((location, length))
    return str(found.string()) if found is not None else ""


RETURN_KEYS = (36, 76)  # Return, keypad Enter
NAVIGATION_KEYS = (115, 116, 117, 119, 121, 123, 124, 125, 126)  # Home, PgUp, forward Delete, End, PgDn, arrows
def selection(client):
    """The text box's selection (location, length), or None when the app does not say."""
    try:
        return tuple(span(client.selectedRange()))
    except Exception:
        return None


def marked(text):
    """The composition as the design draws it: one plain underline in the text colour (apps
    otherwise draw marked text their own way, an accent-coloured thick line in a text view)."""
    return NSAttributedString.alloc().initWithString_attributes_(
        text, {"NSUnderline": 1, "NSUnderlineColor": NSColor.textColor()})



def unmark(client):
    """Clear cd_AI's marked text, if there is any: with nothing marked, empty marked text replaces
    the app's selection (NSTextInputClient), which would delete a selected word."""
    try:
        found = client.markedRange()
        length = span(found)[1]
    except Exception:
        length = 1  # cannot tell: clear it
    if length:
        client.setMarkedText_selectionRange_replacementRange_("", (0, 0), (NSNotFound, 0))

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
            PANEL, OVERLAY, TOAST = Panel(), Overlay(), Panel(toast=True)
        self.drawn = None  # the panel as last drawn (Composition.panel()), redrawn when it changes
        self.kept_menu = None  # the input menu, built once
        self.dead_state = 0  # UCKeyTranslate's dead-key state: an accent waiting for its letter
        self.caret_known = True  # the app gave a caret position (no ghost without one)
        self.ghost_at, self.ghost_checked = None, 0  # where the suggestion was drawn, and when last checked
        return self

    def activateServer_(self, sender):
        objc.super(ClaudishInputController, self).activateServer_(sender)
        self.active = True
        if OWNER[0] is not None and OWNER[0] is not self:
            # The text box before this one has not been told yet (its deactivation can come late):
            # what it showed is not this box's.
            OWNER[0].hide_panel()
            TOAST.hide()
            OVERLAY.hide()
        OWNER[0] = self
        self.shift.cancel()  # a Shift pressed elsewhere is not half a tap here (as Windows at a focus change)
        if self.worker is None:
            self.worker = Suggestions()
        self.worker.watch(True)
        if self.timer is None:
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.04, self, "pollSuggestions:", None, True)
        pill = self.state.returned(self.app(self.client()))  # back where an exchange was held
        if pill:
            self.show_toast(pill, lasting=True)  # it waits for your next key, as the design says

    def deactivateServer_(self, sender):
        try:
            self.finish(self.client())
        except Exception:  # the client went (its window closed): still stop below
            trace("deactivate failed", traceback.format_exc())
        finally:
            self.pause()
        objc.super(ClaudishInputController, self).deactivateServer_(sender)

    def inputControllerWillClose(self):
        self.stop()

    def menu(self):
        """The input menu's items for cd_AI (the menu bar's input source menu): Settings… (a Shift
        tap switches modes, and macOS shows the new input mode). macOS asks after nearly every key: one menu
        per controller, as Squirrel keeps one."""
        try:
            menu = self.kept_menu
            if menu is None:
                menu = self.kept_menu = self.build_menu()
            return menu
        except Exception:
            trace("menu failed", traceback.format_exc())
            raise

    @objc.python_method
    def build_menu(self):
        from AppKit import NSMenu, NSMenuItem
        menu = NSMenu.alloc().initWithTitle_("cd_AI")
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Settings…", "showSettings:", "")
        item.setTarget_(self)
        menu.addItem_(item)
        trace("menu", [str(item.title()) for item in menu.itemArray()])
        return menu

    def showSettings_(self, sender):
        """cd_AI's settings in the browser (claudish.client.show_settings)."""
        import subprocess
        from claudish.client import show_settings

        def opened(link):
            subprocess.run(["/usr/bin/open", link], check=False, timeout=10)
            trace("settings opened")
        show_settings(opened, lambda error: trace("settings failed", "%s: %s" % (type(error).__name__, error)))

    @objc.python_method
    def pause(self):
        """Focus went elsewhere: nothing shows, but the worker stays, so a held exchange's answer
        is there when you come back (as on IBus)."""
        self.active = False
        self.shift.cancel()
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None
        if self.worker is not None:
            self.worker.watch(False)
        self.state.change("")
        if OWNER[0] is not self:  # another text box's controller draws them now
            self.drawn = None  # (drawn again when this one is in use again)
            return
        OWNER[0] = None
        self.hide_panel()
        TOAST.hide()  # a toast belongs to the text box it was shown at, which is gone
        OVERLAY.hide()

    def stop(self):
        self.pause()
        if self.worker is not None:
            self.worker.close()
            self.worker = None

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
        if not self.active or self.worker is None or secure_input():  # results wait: nothing is drawn
            return
        if self.state.follow(self.worker):  # the service stopped or came back
            trace({True: "offline", False: "online"}.get(self.state.offline, self.state.offline))
            if self.state.text and not self.state.live:
                self.show_panel()
        result = self.worker.poll()
        if result:
            trace("result", sorted(result[1]), "current" if result[0] == self.state.revision else "stale")
        drawn = (self.state.drawn, self.state.drawn_cursor)
        kind = self.state.receive(*result) if result else None
        if kind == "text":
            if self.state.converted:  # the rewrite you asked for with Tab: in the panel, your words stay marked
                client = self.client()
                if client is not None:
                    self.changed(client)
                return
            if self.state.live:  # continue: the rest of the sentence, in grey after the caret
                client = self.client()
                if client is not None:
                    self.show_ghost(client)
                return
        elif kind == "done":
            client = self.client()  # a helper took the task: nothing to insert
            if client is not None:
                if self.state.text:  # words you typed meanwhile: they stay, marked
                    self.changed(client)
                else:
                    unmark(client)
        if kind != "done" and not self.state.live and drawn != (self.state.drawn, self.state.drawn_cursor):
            client = self.client()  # a question, a draft or a failure: words set aside or brought back
            if client is not None:
                self.mark(client)
        self.check_ghost()
        if self.state.panel() != self.drawn:  # an answer, a question, progress, or the pause for the keys
            self.show_panel()
        if kind == "done":
            self.show_toast(self.state.done_toast(result[1]["done"]))

    @objc.python_method
    def pick(self, number):
        """A click on a row of the panel (1-based): taken as its key would take it."""
        if not self.active:
            return
        action = self.state.click(number - 1)
        if action == "choose":  # a question's choice: answered, as Tab would
            chosen = self.state.answer_choice()
            if chosen and self.worker is not None:
                self.worker.answer(*chosen)
            client = self.client()  # words set aside for the question come back
            if client is not None:
                self.mark(client)
            self.show_panel()
        elif action == "accept":  # a draft: inserted, as Tab would
            self.finish(self.client(), suggested=True)

    @objc.python_method
    def app(self, client):
        """The focused app's bundle identifier (for bindings), such as "com.apple.Terminal"."""
        try:
            return str(client.bundleIdentifier()) if client is not None else None
        except Exception:  # Not every client implements it.
            return None

    @objc.python_method
    def caret(self, client, start=False):
        """The caret's line in screen coordinates ((x, y), (w, h)), y at the line's bottom, for the
        overlay; with start, where the composition starts (the caret when nothing is composed), for
        the panel and the toasts, as CJK candidate windows sit (docs/design/design.md, Placement).
        IMK's lineHeightRectangle is what input methods place windows by; firstRectForCharacterRange
        came back with y at the line's top in our tests, so it is the fallback, corrected for that."""
        try:
            location = span(client.selectedRange())[0]
            marked = span(client.markedRange())
            if start and marked[0] != NSNotFound and marked[1]:
                location = marked[0]
        except Exception:
            location, marked = 0, (NSNotFound, 0)
        # IMK's index is relative to the inline session, or zero for the current selection
        # when there is none. NSTextInputClient's fallback below takes a document range.
        index = max(0, location - marked[0]) if marked[0] != NSNotFound and marked[1] else 0
        try:
            found = client.attributesForCharacterIndex_lineHeightRectangle_(index, None)
            rect = found[1] if isinstance(found, tuple) and len(found) == 2 else None
            if rect is not None:
                (x, y), (w, h) = unpack(rect)
                if h > 0 and (x, y) != (0, 0):  # the screen's corner: the app did not say
                    trace("caret line", round(x), round(y), round(w), round(h), "inline", index, "document", location)
                    self.caret_known = True
                    return (x, y), (w, h)
        except Exception:
            trace("caret line failed", traceback.format_exc().splitlines()[-1])
        try:
            found = client.firstRectForCharacterRange_actualRange_((location, 0), None)
            rect = found[0] if isinstance(found, tuple) and len(found) == 2 and not hasattr(found, "origin") else found
            (x, y), (w, h) = unpack(rect)
            if h > 0 and (x, y) != (0, 0):
                trace("caret first", round(x), round(y), round(w), round(h), "at", location)
                self.caret_known = True
                return (x, y - h), (w, h)
        except Exception:
            trace("caret failed", traceback.format_exc().splitlines()[-1])
        # No caret from the app: under the pointer, where the person is looking, not a corner.
        self.caret_known = False
        pointer = NSEvent.mouseLocation()
        trace("caret unknown: at the pointer")
        return (pointer.x, pointer.y - 18), (0, 18)

    @objc.python_method
    def show_ghost(self, client):
        """Continue's suggestion: cd_AI's own grey text right after the caret (docs/design/design.md).
        Continue asks only at the end of a line (inside), so it never covers the app's text."""
        ghost = self.state.ghost
        if not ghost or self.state.inside:  # text after the caret on its line: nothing to cover it with
            OVERLAY.hide()
            return
        before = self.around_caret(client)[0] if client is not None else ""
        if before != getattr(self, "asked_before", before) and not self.state.caret_stayed(before):
            # A click moved the caret while it was asked for (no key says so): the text before it is
            # neither what it was when asked (the app may still be catching up after the key, as
            # Chromium's does) nor what continue typed (the app may have changed it: smart quotes,
            # autocorrect, a no-break space). Not for this spot.
            self.state.change("")  # and continue starts again from the app's text there
            OVERLAY.hide()
            return
        self.ghost_at = self.caret(client)
        if not self.caret_known:  # the app gives no caret: nothing to put it after
            self.state.dismiss()
            OVERLAY.hide()
            return
        self.ghost_checked = time.monotonic()
        OVERLAY.show(self.ghost_at, ghost)
        trace("ghost overlay", len(ghost))

    @objc.python_method
    def check_ghost(self, now=False):
        """macOS tells an input method nothing when the caret moves without a key (a click, a
        scroll, the window moving): while the suggestion shows, look at the caret a few times a
        second, and when it moved (or the text box is gone) drop the suggestion: Tab must never
        take one you no longer see. now: at once (Tab is about to take it)."""
        if not OVERLAY.visible():
            if now and self.state.ghost:  # not on screen (hidden from elsewhere): Tab takes nothing
                self.state.dismiss()
            return
        if not now and time.monotonic() - self.ghost_checked < 0.25:
            return
        self.ghost_checked = time.monotonic()
        client = self.client()
        if client is not None and self.caret(client) == self.ghost_at:
            return
        OVERLAY.hide()
        self.state.dismiss()
        trace("ghost dropped: the caret moved")

    @objc.python_method
    def show_panel(self, client=None):
        """The panel at the caret, as Composition.panel() describes it; nothing in continue."""
        spec = self.state.panel()
        client = client if client is not None else self.client()
        if not spec or client is None:
            self.hide_panel()
            return
        TOAST.hide()  # a panel replaces a toast at the caret
        PANEL.show(self.caret(client, start=True), spec, self.pick)
        trace("panel", len(spec["rows"]), "rows", "lit" if spec.get("nudge") else "plain")  # no text
        self.drawn = spec

    @objc.python_method
    def show_toast(self, spec, client=None, lasting=False):
        """A panel at the caret: briefly (what Esc just dropped; the mode switch with MODE_TOAST), or until your next
        key (lasting: the pill for an exchange held while you were away)."""
        client = client if client is not None else self.client()
        if client is None or spec is None:  # nothing to say (hints off)
            return
        TOAST.show(self.caret(client, start=True), spec)
        if TOAST_TIMER[0] is not None:
            TOAST_TIMER[0].invalidate()  # a newer toast gets its own two seconds, a pill none (any text box's)
            TOAST_TIMER[0] = None
        if lasting:  # a pill: until a key or a focus change ends it
            return
        TOAST_TIMER[0] = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            2.0, self, "hideToast:", None, False)

    @objc.signature(b"v@:@")
    def hideToast_(self, timer):
        if TOAST_TIMER[0] is timer or TOAST_TIMER[0] is None:
            TOAST_TIMER[0] = None
            TOAST.hide()

    @objc.python_method
    def hide_panel(self):
        PANEL.hide()
        self.drawn = None

    @objc.python_method
    def follow_caret(self, client):
        """The suggestion moved with the caret by a key cd_AI marked (a waiting accent): drawn at
        the caret again, so the caret check does not take it for a click elsewhere."""
        if self.state.ghost and self.ghost_at is not None:
            self.ghost_at = self.caret(client)
            OVERLAY.show(self.ghost_at, self.state.ghost)

    @objc.python_method
    def switch_mode(self, client, tell=True):
        """A Shift tap, or a mode picked in the input menu: continue <-> compose. Leaving compose
        keeps what you see, as typed. tell: select the mode, so the menu bar shows its icon."""
        kept = self.state.toggle()
        if self.worker is not None:
            self.worker.schedule(self.state.revision, "")  # what was asked belongs to the old mode
        if kept:
            client.insertText_replacementRange_(kept, (NSNotFound, 0))
        else:  # an instruction held with its exchange: it leaves the text box (continue marks nothing)
            unmark(client)
        self.changed(client)
        spec, lasting = self.state.switched()
        if lasting or MODE_TOAST:  # the held exchange's pill; macOS says the mode itself
            self.show_toast(spec, client, lasting=lasting)
        if tell:
            try:
                client.selectInputMode_(MODE_IDS[self.state.mode])
            except Exception:  # not every client implements it
                trace("select mode failed", traceback.format_exc())

    def setValue_forTag_client_(self, value, tag, sender):
        """A mode picked in the input menu (or cd_AI selected in a mode): switch to it as a Shift
        tap does."""
        trace("mode", tag == INPUT_MODE_TAG, value)
        modes = {mode_id: mode for mode, mode_id in MODE_IDS.items()}
        if tag != INPUT_MODE_TAG or str(value) not in modes or getattr(self, "state", None) is None:
            return
        client = self.client()
        if client is not None and self.state.mode != modes[str(value)]:
            self.switch_mode(client, tell=False)

    @objc.python_method
    def take_selection(self, client):
        """Tab with nothing composed: the app's selection becomes the composition, as if you had just
        typed it (marked in its place); then Tab rewrites it, Shift+Enter sends it. True when taken."""
        try:
            selected = client.selectedRange()
            location, length = span(selected)
            if location == NSNotFound or not 0 < length <= MAX_COMPOSITION:
                return False
            text = substring(client, location, length)
        except Exception:
            return False
        if not self.state.selectable(text):  # long or multi-line: Tab is the app's
            return False
        self.state.change(text)
        client.setMarkedText_selectionRange_replacementRange_(marked(text), (units(text), 0), (location, length))
        return True

    @objc.python_method
    def around_caret(self, client):
        """(before, after): the client's text around the caret (IMKTextInput), or empty when it does
        not share it. Chromium-based apps (VS Code, browsers) answer only about 100 characters
        around the selection; native text views answer the whole text."""
        def text(location, length):
            return substring(client, location, length) if length > 0 else ""
        try:
            location, length = span(client.selectedRange())
            marked = span(client.markedRange())  # our own composition or suggestion is not the app's text
            if marked[0] != NSNotFound and marked[1]:
                location, length = marked
            total = client.length()
            if location == NSNotFound or location > total:
                return "", ""
            start = max(0, location - AROUND)
            end = min(total, location + length)
            return text(start, location - start), text(end, min(AROUND, total - end))
        except Exception:  # not every client implements these
            return "", ""

    @objc.python_method
    def changed(self, client):
        self.state.field(terminal=is_terminal(self.app(client)))  # a terminal's command line is not prose
        before, after = self.around_caret(client) if self.state.live else ("", "")
        after = self.state.caret_after(after)
        self.asked_before = before  # the app's text where continue asks from (see show_ghost)
        trace("changed", self.state.mode, "asks" if self.state.automatic else "waits")
        if self.worker is not None and self.state.automatic:  # continue: what follows the caret too
            self.worker.schedule(self.state.revision, self.state.text, self.state.mode, app=self.app(client),
                                 after=after)
        elif self.worker is not None and not self.state.text:
            self.worker.schedule(self.state.revision, "")
        if self.state.live:  # the only thing shown is the suggestion, with the caret before it
            self.hide_panel()
            self.show_ghost(client)
            return
        OVERLAY.hide()
        self.mark(client)
        self.show_panel(client)  # what is waiting (drafts, a question) or the one short hint

    @objc.python_method
    def mark(self, client):
        """The marked text: your words (a rewrite waits in the panel for Tab), a waiting accent."""
        shown = self.state.drawn
        # Cocoa ranges count UTF-16 code units, rather than Python code points; the cursor is where
        # ← and → left it (the end by default).
        cursor = units(shown[:self.state.drawn_cursor])
        if shown:
            client.setMarkedText_selectionRange_replacementRange_(marked(shown), (cursor, 0), (NSNotFound, 0))
        else:  # empty marked text would leave a terminal composing: the next Return beeps
            unmark(client)

    @objc.python_method
    def dead_key(self, key, chars, flags):
        """(its accent, the layout's dead-key state) when the keyboard layout says this key is dead
        (Spanish ´, French ^, U.S. Option+e); where the layout cannot be read, the U.S. Option keys."""
        found = layout().dead(key, flags) if layout() is not None else None
        if found is not None:
            return (found[1] or chars, found[0]) if found and (found[1] or chars) else None
        return (chars, 0) if flags & NSEventModifierFlagOption and chars in ACCENTS else None

    @objc.python_method
    def with_accent(self, key, chars, flags, accent):
        """What a waiting accent and this key make, as the layout makes it (´ then t is ´t)."""
        reader, state = layout(), self.dead_state
        if reader is not None and state:
            made = reader.translate(key, flags, state)
            if made and made[0]:
                return made[0]
        return accented(accent, chars[0]) + chars[1:] if accent in ACCENTS else accent + chars

    @objc.python_method
    def live_key(self, client, key, chars, flags=0):
        """Continue mode: keys go to the app as typed; Tab takes the suggestion, Esc dismisses it."""
        state = self.state
        accent, state.accent = state.accent, ""
        found = self.dead_key(key, chars, flags)
        if found and found[0] != accent:  # a dead key: its accent waits, shown (twice: the accent itself)
            state.accent, self.dead_state = found
            client.setMarkedText_selectionRange_replacementRange_(marked(state.accent), (len(state.accent), 0),
                                                                  (NSNotFound, 0))
            self.follow_caret(client)  # the suggestion stays after the accent, not under it
            return True
        if accent:
            unmark(client)
            if key in (51, 53):
                self.follow_caret(client)
                return True  # Backspace or Esc cancels the accent, and nothing else
            if chars and all(typeable(char) for char in chars):
                chars = self.with_accent(key, chars, flags, accent)  # é, not the e the key would type
        if key == 48 and not flags & (NSEventModifierFlagShift | NSEventModifierFlagOption):  # Tab (Shift+Tab, Option+Tab: the app's)
            self.check_ghost(now=True)  # a click since the last look: the suggestion is not there any more
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
        navigation = key in RETURN_KEYS + (51,) + NAVIGATION_KEYS
        if navigation or not chars or not chars.isprintable():
            if key == 51 and state.text:
                state.backspace()
            else:
                state.change("")  # Enter, arrows, anything else: the context starts over
            self.changed(client)  # clears the suggestion before the app handles the key
            return False
        before = self.around_caret(client)[0]
        # A fresh start (a paste, a new field), or a click since (no key says so): from the app's text.
        if not state.text or not state.caret_stayed(before):
            state.change(before[-MAX_COMPOSITION:])
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
                unmark(client)
            return
        if self.state.for_model and not suggested:
            # The app ends the composition (a click, a focus change): the instruction is not text
            # for the app; its exchange is held for this app, its work going on, offered when you
            # come back.
            self.state.leave(self.app(client))
            self.hide_panel()
            if client is not None:
                unmark(client)
            return
        # Your own words, never the model's unless you asked for them (a rewrite waits for Tab).
        text = self.state.commit(suggested)
        if self.worker is not None:
            self.worker.schedule(self.state.revision, "")
        self.hide_panel()
        self.state.accent = ""  # a waiting accent is never committed
        if text and client is not None:
            # Inserting replaces the client's existing marked text.
            client.insertText_replacementRange_(text, (NSNotFound, 0))
        elif client is not None:
            unmark(client)  # nothing to insert: a waiting accent marked alone goes
        if self.state.text and client is not None:  # words that stay are the next composition, marked
            self.changed(client)

    def commitComposition_(self, sender):
        self.shift.cancel()  # the app ended it (a Shift+click): that Shift is no tap
        self.finish(self.client())

    def handleEvent_client_(self, event, client):
        try:
            handled = self.handle(event, client)
            special = {36: "Return", 48: "Tab", 51: "Backspace", 53: "Escape", 56: "Shift", 60: "Shift", 100: "F8"}
            trace("key", special.get(event.keyCode(), "char"), self.state.mode, "handled" if handled else "passed")
            return handled
        except Exception:
            trace("key failed", traceback.format_exc())
            raise

    @objc.python_method
    def handle(self, event, client):
        if secure_input():  # a password field: straight in, nothing shown, nothing sent
            if self.state.text or self.state.ghost or self.state.accent:  # it came on while composing (Secure Keyboard Entry):
                self.finish(client)  # your words go in first, as on a focus change; no suggestion stays
                self.state.dismiss()
            self.hide_panel()
            OVERLAY.hide()
            TOAST.hide()
            return False
        if self.active and event.type() == NSEventTypeFlagsChanged:
            if event.keyCode() in (56, 60):  # left or right Shift, pressed or released
                chord = bool(event.modifierFlags() & (NSEventModifierFlagControl | NSEventModifierFlagOption |
                                                      NSEventModifierFlagCommand))
                if event.modifierFlags() & NSEventModifierFlagShift:
                    self.shift.press(time.monotonic(), chord)
                    self.shift_range = selection(client)
                else:
                    # A Shift+click sends no key: the selection or caret it moved says so.
                    clicked = selection(client) != getattr(self, "shift_range", None)
                    if self.shift.release(time.monotonic(), chord or clicked):
                        self.switch_mode(client)
            else:
                self.shift.other()
            return False  # the app still sees its modifiers
        if not self.active or event.type() != NSEventTypeKeyDown:
            return False
        self.shift.other()
        TOAST.hide()  # a key ends a toast: it was said where the caret was
        flags = event.modifierFlags()
        # Option types characters such as — and €; it is not a shortcut by itself.
        if flags & (NSEventModifierFlagCommand | NSEventModifierFlagControl):
            self.finish(client)
            return False
        self.pollSuggestions_(None)
        key = event.keyCode()
        chars = event.characters() or ""
        # Choices are not numbered: digits are text in English, as Space is (↑/↓, then Tab).
        if key == 100 and self.state.toggle_look():  # F8 while composing: a picture of this window goes with the instruction.
            self.changed(client)
            return True
        if self.state.live:
            return self.live_key(client, key, chars, flags)
        # Option+e, Option+u, ...: a dead key gives its accent alone; it waits for its letter (the
        # next key takes it, Backspace cancels it, any other key drops it).
        accent, self.state.accent = self.state.accent, ""
        found = self.dead_key(key, chars, flags)
        if found and found[0] != accent:  # twice: the accent itself
            self.state.accent, self.dead_state = found
            self.changed(client)
            return True
        if accent and key in (51, 53):  # Backspace or Esc cancels the accent, and nothing else
            self.changed(client)
            return True
        if accent and not self.state.text:
            unmark(client)  # the accent alone was marked: it goes before the key does (Esc, Return, an arrow)
        elif accent:  # dropped: your words are marked again without it (Tab or an arrow may draw nothing)
            shown = self.state.drawn
            client.setMarkedText_selectionRange_replacementRange_(marked(shown), (units(shown[:self.state.drawn_cursor]), 0),
                                                                  (NSNotFound, 0))
        if key in (36, 76, 51, 48) and flags & NSEventModifierFlagOption:
            # Option+Return (a newline in chat apps), Option+Backspace (delete a word) and Option+Tab (a
            # tab in a table cell) are the app's, as Alt with them is on Linux and Windows: your words go in first.
            self.finish(client)
            return False
        shift = bool(flags & NSEventModifierFlagShift)
        if key in RETURN_KEYS and not self.state.talks(shift) and self.state.text:
            kept = self.state.keep()  # the keeper key: as it is, and keep composing
            if kept is not None:  # inserting ends the composition: no empty marked text before the key
                client.insertText_replacementRange_(kept, (NSNotFound, 0))
            self.changed(client)
            # Enter commits (or, once the model is asked, does nothing), as other input methods do:
            # press it again for the app.
            return True
        if key in RETURN_KEYS:  # Return, keypad Enter
            action = self.state.enter()  # the summon key talks to the model; it never inserts its text
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
                                         app=self.app(client), look=self.state.look, before=before, after=after,
                                         draft=self.state.about)
                self.changed(client)  # your instruction stays marked while its exchange is open
            elif action == "wait":  # on the model's text, the panel lights Tab, the key that takes it
                self.show_panel(client)
            return action != "pass"
        if key == 48 and not shift:  # Tab; Shift+Tab commits and is the app's, as a navigation key
            if not self.state.text and self.take_selection(client):  # (continue returned above)
                self.show_panel(client)  # a selection: your words now, as if typed
                return True
            action = self.state.tab()
            if action == "choose":
                chosen = self.state.answer_choice()
                if chosen and self.worker is not None:
                    self.worker.answer(*chosen)
                self.changed(client)
                return True
            if action == "accept":
                answering = self.state.take_answering()  # an answer to read: recorded, not asked again
                if answering and self.worker is not None:
                    self.worker.answer(*answering)
                self.finish(client, suggested=True)
            elif action == "request":  # rewrite: ask now; it waits in the panel when it arrives
                if self.worker is not None:
                    before, after = window(*self.around_caret(client))  # where the rewrite goes, as much as it sends
                    self.worker.schedule(self.state.revision, self.state.text, "rewrite", immediate=True,
                                         app=self.app(client), before=before, after=after)
            elif action == "convert":
                self.changed(client)
            return action != "pass"
        if key in (126, 125) and self.state.move(-1 if key == 126 else 1):  # ↑ and ↓ move the highlight
            self.show_panel(client)
            return True
        if key == 53 and flags & NSEventModifierFlagShift and self.state.restore():  # Shift+Esc: the dropped one, back
            # A held exchange's request is still running: its results come for the same revision.
            self.changed(client)
            return True
        if key == 53 and flags & NSEventModifierFlagShift and self.state.text:
            return True  # composing, Shift+Esc brings nothing back, and never drops what you typed
        if key == 53:  # Escape: one step back
            action = self.state.escape()
            if action == "dismiss":  # an answer to read: Dismiss, nothing inserted
                chosen = self.state.dismissal()
                if chosen and self.worker is not None:
                    self.worker.answer(*chosen)
                self.mark(client)  # words set aside for the question come back
                self.show_panel(client)
                return True
            if action in ("clear", "drop"):  # words discarded: said, with the key that brings them back
                self.show_toast(self.state.dropped_toast(), client)
            if action == "clear":  # the reply goes; the question stays
                self.changed(client)
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
        plain = not flags & (NSEventModifierFlagOption | NSEventModifierFlagShift)  # Option+← and Shift+← navigate
        steps = {123: -1, 124: 1, 115: "home", 119: "end"}  # ← → Home End move in what you type
        if key in steps and plain and self.state.arrow(steps[key]):
            self.changed(client)
            return True
        if key == 117 and plain and self.state.delete():  # forward delete, at the cursor
            self.changed(client)
            return True
        text = event.characters() or ""
        if accent and text and all(typeable(char) for char in text):
            text = self.with_accent(key, text, flags, accent)  # é from ´ then e, as macOS makes it in a text field
        # Navigation keys use private-use characters, which must not enter the draft.
        if key in NAVIGATION_KEYS or not all(typeable(char) for char in text) or not text:
            self.finish(client)
            return False
        if all(self.state.passes(char) for char in text):  # nothing composed: the space is the app's text
            client.insertText_replacementRange_(text, (NSNotFound, 0))
            return True
        for char in text:
            if not self.state.insert(char):  # full: what is before the cursor goes in
                client.insertText_replacementRange_(self.state.make_room(char), (NSNotFound, 0))
        self.changed(client)
        return True
