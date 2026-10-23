"""cd_AI's own panel and suggestion overlay on macOS (the visual pass, G45; docs/design/design.md).

The panel draws Composition.panel()'s description as the design lab does (claudish/web/design.html,
macOS skin): an optional header (a small label, then the content as is), rows (the highlighted
one a neutral fill with the system accent bar and the key that takes it), and one footer (the AI
tile or a warning mark, what is happening, each key with its verb, a hosted model's name). The
overlay draws continue's suggestion right after the caret, in the system font at the caret's
height. Non-activating panels: the app keeps the keyboard; a click on a row picks it.
"""
import objc
from AppKit import (NSBackingStoreBuffered, NSBezierPath, NSColor, NSEdgeInsetsMake, NSFont, NSFontWeightBold,
                    NSFontWeightMedium, NSFontWeightRegular, NSFontWeightSemibold, NSImage, NSMakeRect, NSPanel,
                    NSMutableParagraphStyle, NSProgressIndicator, NSScreen, NSTextField, NSView, NSVisualEffectView)

PAD, ROW_X, ROW_Y, KEY_GAP, RADIUS, ROW_RADIUS = 5, 9, 4, 6, 12, 7
SIZE, SMALL, MIN_WIDTH, MAX_WIDTH, TAKE = 14, 12, 240, 440, 30
BORDERLESS, NONACTIVATING = 0, 1 << 7  # NSWindowStyleMask values
POPUP_LEVEL = 101  # NSPopUpMenuWindowLevel: above the app's own windows
MATERIAL_MENU, BLENDING_BEHIND, STATE_ACTIVE = 5, 0, 1
ACCENT = (217 / 255, 119 / 255, 87 / 255)  # Claudish's: the AI tile only
KEYS = {"Enter": "↩", "Esc": "esc", "Tab": "⇥", "Shift": "⇧", "Shift+Enter": "⇧↩", "Shift+Esc": "⇧esc"}  # macOS menus' names


def spec_take(spec):
    return (spec or {}).get("take") or "Enter"


def rounded_mask(radius):
    """A stretchable rounded-rectangle mask: a visual-effect view clips its material only to a
    mask image (a layer's corner radius leaves square corners of material behind)."""
    edge = 2 * radius + 1

    def draw(rect):
        NSColor.blackColor().set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius).fill()
        return True
    image = NSImage.imageWithSize_flipped_drawingHandler_((edge, edge), False, draw)
    image.setCapInsets_(NSEdgeInsetsMake(radius, radius, radius, radius))
    image.setResizingMode_(1)  # NSImageResizingModeStretch
    return image


def label(text, size=SIZE, weight=NSFontWeightRegular, color=None, mono=False, width=None):
    field = NSTextField.labelWithString_(text)
    field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(size, weight) if mono
                   else NSFont.systemFontOfSize_weight_(size, weight))
    field.setTextColor_(color or NSColor.labelColor())
    if width:
        field.setPreferredMaxLayoutWidth_(width)
        field.cell().setWraps_(True)
        field.setLineBreakMode_(0)  # NSLineBreakByWordWrapping
    return field


class Box(NSView):
    """A rounded rectangle in a colour, drawn by AppKit (a layer's CGColor needs Quartz's bridge)."""

    def drawRect_(self, rect):
        self.color.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), self.radius, self.radius).fill()


def box(color, radius):
    view = Box.alloc().initWithFrame_(NSMakeRect(0, 0, 1, 1))
    view.color, view.radius = color, radius
    return view


def tile(text, background, foreground, round_=False):
    """The footer's mark: the AI tile, or a warning mark when a request failed."""
    view = box(background, 9 if round_ else 4)
    view.setFrame_(NSMakeRect(0, 0, 18, 18))
    glyph = label(text, 12 if round_ else 10, NSFontWeightBold, foreground, mono=not round_)
    size = glyph.fittingSize()
    glyph.setFrame_(NSMakeRect((18 - size.width) / 2, (18 - size.height) / 2, size.width, size.height))
    view.addSubview_(glyph)
    return view


def key_label(key, lit=False, size=SMALL):
    """A key's glyph, bare as in macOS menus: at its words' size (the system font draws ⇥ ↩ ↑↓
    to sit on the text's baseline, as in a menu's shortcuts), heavier and at full contrast
    (round 5: the hint's grey was too faint); lit on a draft's row after Enter: a keycap, as on
    every platform (the accent's outline, tinted inside; kit.css .k-cap.lit)."""
    glyph = label(KEYS.get(key, key), size, NSFontWeightSemibold)
    if not lit:
        return glyph
    inside = glyph.fittingSize()
    accent = NSColor.controlAccentColor()
    outline = box(accent, 4)
    outline.setFrame_(NSMakeRect(0, 0, inside.width + 10, inside.height + 2))
    tint = box(accent.blendedColorWithFraction_ofColor_(0.8, NSColor.windowBackgroundColor()), 3)
    tint.setFrame_(NSMakeRect(1, 1, inside.width + 8, inside.height))
    outline.addSubview_(tint)
    glyph.setFrame_(NSMakeRect(5, 1, inside.width, inside.height))
    outline.addSubview_(glyph)
    return outline


class Row(NSView):
    """A row the mouse can pick: a click calls back with its number."""

    def initWithFrame_(self, frame):
        self = objc.super(Row, self).initWithFrame_(frame)
        if self is not None:
            self.picked = None
        return self

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        if self.picked is not None:
            self.picked()


class Panel:
    """The panel next to the caret: show(rect, spec, pick), hide()."""

    def __init__(self):
        self.window = None
        self.opened = None  # (x, line y) where the panel opened: it stays there while it is open

    def build(self):
        window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, MIN_WIDTH, 40), BORDERLESS | NONACTIVATING, NSBackingStoreBuffered, False)
        window.setLevel_(POPUP_LEVEL)
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setHasShadow_(True)
        window.setHidesOnDeactivate_(False)
        window.setFloatingPanel_(True)
        window.setBecomesKeyOnlyIfNeeded_(True)
        effect = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, MIN_WIDTH, 40))
        effect.setMaterial_(MATERIAL_MENU)
        effect.setBlendingMode_(BLENDING_BEHIND)
        effect.setState_(STATE_ACTIVE)
        effect.setMaskImage_(rounded_mask(RADIUS))
        window.setContentView_(effect)
        self.window, self.effect = window, effect

    def show(self, rect, spec, pick=None):
        """rect: the caret's line in screen coordinates ((x, y), (w, h)); spec: Composition.panel();
        pick(number): a click on a row."""
        if self.window is None:
            self.build()
        self.spec = spec
        for view in list(self.effect.subviews()):
            view.removeFromSuperview()
        inner = MAX_WIDTH - 2 * PAD - 2 * ROW_X
        secondary = NSColor.secondaryLabelColor()
        blocks = []  # (kind, views, height), laid out top to bottom
        widest = MIN_WIDTH if spec["rows"] or spec["body"] or spec.get("thread") else 0
        for turn in spec.get("thread") or []:
            # Your earlier turns: one line, your words at full size and colour, underlined as they
            # were at the caret; the label is the muted part.
            line = label("%s  %s" % (turn["label"], turn["body"]), SIZE)
            words = line.attributedStringValue().mutableCopy()
            words.addAttribute_value_range_("NSFont", NSFont.systemFontOfSize_weight_(SMALL, NSFontWeightSemibold),
                                            (0, len(turn["label"])))
            words.addAttribute_value_range_("NSColor", secondary, (0, len(turn["label"])))
            words.addAttribute_value_range_("NSUnderline", 1, (len(turn["label"]) + 2, len(turn["body"])))
            one_line = NSMutableParagraphStyle.alloc().init()
            one_line.setLineBreakMode_(4)  # NSLineBreakByTruncatingTail: "thanking them fo…", as the lab does
            words.addAttribute_value_range_("NSParagraphStyle", one_line, (0, words.length()))
            line.setAttributedStringValue_(words)
            line.setLineBreakMode_(4)
            widest = max(widest, min(inner, line.fittingSize().width) + 2 * (PAD + ROW_X))
            blocks.append(("turn", line, line.fittingSize().height + ROW_Y + 2))
        if spec["body"]:
            views = []
            if spec["label"]:
                views.append(label(spec["label"], SMALL, NSFontWeightSemibold, secondary, width=inner))
            views.append(label(spec["body"], SIZE - 1 if spec["code"] else SIZE, mono=spec["code"], width=inner))
            widest = max([widest] + [v.fittingSize().width + 2 * (PAD + ROW_X) for v in views])
            blocks.append(("head", views, sum(v.fittingSize().height for v in views) + 2 * (len(views) - 1) + 2 * ROW_Y + 1))
        takes = spec["on"] >= 0  # every row keeps the column for the highlighted row's key
        text_width = inner - (TAKE if takes else 0)
        replying = spec.get("replying")  # you are typing a reply at the caret: the choices fade
        for index, row in enumerate(spec["rows"]):
            on = index == spec["on"]
            legend = " — " + row["legend"] if row.get("legend") else ""
            text = label(row["text"] + legend, SIZE, color=secondary if replying else None, width=text_width)
            if legend:  # the legend in the secondary colour
                words = text.attributedStringValue().mutableCopy()
                words.addAttribute_value_range_("NSColor", secondary, (len(row["text"]), len(legend)))
                text.setAttributedStringValue_(words)
            size = text.fittingSize()
            widest = max(widest, size.width + (TAKE if takes else 0) + 2 * (PAD + ROW_X))
            blocks.append(("row", (text, on, index + 1), max(size.height, 18) + 2 * ROW_Y))
        foot = self.footer(spec, secondary)
        widest = max(widest, sum(self.size(v).width + gap for v, gap in foot) + 2 * (PAD + ROW_X))
        blocks.append(("foot", foot, 20 + 2 * ROW_Y - 1))
        width = min(MAX_WIDTH, widest)
        height = 2 * PAD + sum(h for _, _, h in blocks) + (2 if len(blocks) > 1 else 0)
        y = height - PAD
        for kind, views, h in blocks:
            if kind == "foot" and len(blocks) > 1:
                y -= 2
            y -= h
            getattr(self, "place_" + kind)(views, y, h, width, pick)
        (cx, cy), (cw, ch) = rect
        # Under the caret's line, the content starting at the caret (as on every platform: GNOME
        # knows only the caret). It opens there and stays while it is open on that line and the caret
        # is at or right of it: it never slides while you type (a reply, or more words), and when the
        # text leaves (sent) it moves to the caret.
        x = cx + cw - PAD - ROW_X
        if self.window.isVisible() and self.opened and abs(self.opened[1] - cy) < 2 and x >= self.opened[0]:
            x = self.opened[0]
        self.opened = (x, cy)
        frame = NSMakeRect(x, cy - height - 6, width, height)
        screen = NSScreen.mainScreen().visibleFrame()
        if frame.origin.y < screen.origin.y:  # no room below: above the line
            frame.origin.y = cy + ch + 6
        frame.origin.x = max(screen.origin.x + 4, min(frame.origin.x, screen.origin.x + screen.size.width - width - 4))
        self.window.setFrame_display_(frame, True)
        self.window.invalidateShadow()  # the shadow follows the rounded mask, not the square window
        self.window.orderFrontRegardless()

    @staticmethod
    def size(view):
        return view.frame().size if isinstance(view, (NSProgressIndicator, Box)) else view.fittingSize()

    def footer(self, spec, secondary):
        """[(view, gap after)]: the mark, what is happening, each key with its verb, the tail, and a
        hosted model's name at the end."""
        items = []
        if spec["tile"] == "warn":  # a failure reads without colour: a mark, then why
            items.append((tile("!", NSColor.systemRedColor(), NSColor.whiteColor(), round_=True), 8))
        else:
            items.append((tile("AI", NSColor.colorWithSRGBRed_green_blue_alpha_(*ACCENT, 1), NSColor.whiteColor()), 8))
        if spec["status"]:
            if spec["busy"]:
                spinner = NSProgressIndicator.alloc().initWithFrame_(NSMakeRect(0, 0, 12, 12))
                spinner.setStyle_(1)  # NSProgressIndicatorStyleSpinning
                spinner.setControlSize_(2)  # mini
                spinner.setIndeterminate_(True)
                spinner.startAnimation_(None)
                items.append((spinner, 6))
            items.append((label(spec["status"], SMALL), 12))
        if spec["failed"]:
            items.append((label(spec["failed"], SMALL, color=NSColor.systemRedColor()), 12))
        for key, verb in spec["foot"]:
            items.append((key_label(key), KEY_GAP - 2))
            items.append((label(verb, SMALL, color=secondary), 12))
        if spec["tail"]:
            items.append((label(spec["tail"], SMALL, color=secondary), 12))
        if spec["mark"]:
            items.append((label(spec["mark"], SMALL, color=secondary), 0))
        return items

    def place_turn(self, line, y, h, width, pick):
        size = line.fittingSize()
        line.setFrame_(NSMakeRect(PAD + ROW_X, y + 1, width - 2 * (PAD + ROW_X), size.height))
        self.effect.addSubview_(line)

    def place_head(self, views, y, h, width, pick):
        top = y + h - ROW_Y - 1
        for view in views:
            size = view.fittingSize()
            top -= size.height
            view.setFrame_(NSMakeRect(PAD + ROW_X, top, width - 2 * (PAD + ROW_X), size.height))
            self.effect.addSubview_(view)
            top -= 2

    def place_row(self, parts, y, h, width, pick):
        text, on, picked = parts
        row = Row.alloc().initWithFrame_(NSMakeRect(PAD, y, width - 2 * PAD, h))
        if pick is not None:
            row.picked = lambda: pick(picked)
        if on:  # a neutral fill, the system accent bar inside it, and the row's own ↩
            fill = box(NSColor.labelColor().colorWithAlphaComponent_(0.07), ROW_RADIUS)
            fill.setFrame_(NSMakeRect(0, 0, width - 2 * PAD, h))
            row.addSubview_(fill)
            bar = box(NSColor.controlAccentColor(), 1.5)
            bar.setFrame_(NSMakeRect(2, 7, 3, h - 14))
            row.addSubview_(bar)
            key = spec_take(self.spec)  # Tab takes a draft; Enter confirms a choice
            take = key_label(key, bool(self.spec.get("nudge")))
            size = take.frame().size if self.spec.get("nudge") else take.fittingSize()
            take.setFrame_(NSMakeRect(width - 2 * PAD - ROW_X - size.width, (h - size.height) / 2, size.width, size.height))
            row.addSubview_(take)
        text.setFrame_(NSMakeRect(ROW_X, ROW_Y, text.fittingSize().width, h - 2 * ROW_Y))
        row.addSubview_(text)
        self.effect.addSubview_(row)

    def place_foot(self, items, y, h, width, pick):
        # One line through the footer's middle: every key and word in one size on one baseline,
        # their lowercase centred on it (as a menu's shortcuts sit with its titles), the tile and
        # the spinner centred on it. Keys in a larger size never lined up with their words.
        middle = y + h / 2
        baseline = middle - NSFont.systemFontOfSize_(SMALL).xHeight() / 2
        x = PAD + ROW_X
        for index, (view, gap) in enumerate(items):
            size = self.size(view)
            if index == len(items) - 1 and gap == 0 and index:  # the hosted mark, at the end
                x = max(x, width - PAD - ROW_X - size.width)
            if isinstance(view, NSTextField):
                bottom = baseline + view.font().descender()  # descender is negative
            else:
                bottom = middle - size.height / 2
            view.setFrame_(NSMakeRect(x, round(bottom), size.width, size.height))
            self.effect.addSubview_(view)
            x += size.width + gap

    def hide(self):
        if self.window is not None:
            self.window.orderOut_(None)


class Overlay:
    """Continue's suggestion: cd_AI's own grey text right after the caret, in the system font at
    the caret's height (docs/design/design.md), never typed."""

    def __init__(self):
        self.window = None

    def show(self, rect, text):
        if self.window is None:
            self.window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 10, 10), BORDERLESS | NONACTIVATING, NSBackingStoreBuffered, False)
            self.window.setLevel_(POPUP_LEVEL)
            self.window.setOpaque_(False)
            self.window.setBackgroundColor_(NSColor.clearColor())
            self.window.setIgnoresMouseEvents_(True)
            self.window.setHasShadow_(False)
            self.field = NSTextField.labelWithString_("")
            self.window.setContentView_(self.field)
        (cx, cy), (cw, ch) = rect
        self.field.setStringValue_(text)
        self.field.setFont_(NSFont.systemFontOfSize_(max(11.0, round(ch / 1.25))))
        self.field.setTextColor_(NSColor.placeholderTextColor())
        size = self.field.fittingSize()
        self.window.setFrame_display_(NSMakeRect(cx + cw, cy + (ch - size.height) / 2, size.width, size.height), True)
        self.window.orderFrontRegardless()

    def hide(self):
        if self.window is not None:
            self.window.orderOut_(None)

    def visible(self):
        return self.window is not None and bool(self.window.isVisible())
