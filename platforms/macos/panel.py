"""cd_AI's own panel and suggestion overlay on macOS (the visual pass, G45; docs/design/visual.md).

The stock IMKCandidates panel is a fixed, tall list with tiny numbers; IMK also drops colour from
marked text, so continue's suggestion looked typed. This draws both: a panel at the caret sized to
its content (an instruction's drafts, a question as is, an answer to read, one short hint), and the
suggestion as grey text right after the caret. Non-activating panels: the app keeps the keyboard.
"""
from AppKit import (NSBackingStoreBuffered, NSBezierPath, NSColor, NSEdgeInsetsMake, NSFont, NSFontWeightRegular,
                    NSFontWeightSemibold, NSImage, NSMakeRect, NSPanel, NSScreen, NSTextField, NSView,
                    NSVisualEffectView)

from claudish.composition import split_title

PADDING, ROW_GAP, WIDTH, MIN_WIDTH, RADIUS = 12, 4, 440, 220, 10
BORDERLESS, NONACTIVATING = 0, 1 << 7  # NSWindowStyleMask values
POPUP_LEVEL = 101  # NSPopUpMenuWindowLevel: above the app's own windows
MATERIAL_MENU, BLENDING_BEHIND, STATE_ACTIVE = 5, 0, 1


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


def label(text, size=14, weight=NSFontWeightRegular, color=None, mono=False, width=None):
    field = NSTextField.labelWithString_(text)
    field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(size, weight) if mono
                   else NSFont.systemFontOfSize_weight_(size, weight))
    field.setTextColor_(color or NSColor.labelColor())
    if width:
        field.setPreferredMaxLayoutWidth_(width)
        field.cell().setWraps_(True)
        field.setLineBreakMode_(0)  # NSLineBreakByWordWrapping
    return field


class Panel:
    """The list next to the caret: show(rect, title, items, selected, hint), hide()."""

    def __init__(self):
        self.window = None

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

    def show(self, rect, title=None, items=(), selected=0, hint=""):
        """rect: the caret's line in screen coordinates ((x, y), (w, h)), as IMK reports it."""
        if self.window is None:
            self.build()
        for view in list(self.effect.subviews()):
            view.removeFromSuperview()
        rows = []  # (view, x, height) from the top
        inner = WIDTH - 2 * PADDING
        if title:
            header, body = split_title(title)
            if header:
                rows.append((label(header, 11, NSFontWeightSemibold, color=NSColor.secondaryLabelColor()), PADDING))
            rows.append((label(body, 14, width=inner), PADDING))
        for index, text in enumerate(items):
            row = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH - 12, 10))
            number = label(str(index + 1), 11, mono=True,
                           color=NSColor.alternateSelectedControlTextColor() if index == selected
                           else NSColor.tertiaryLabelColor())
            body = label(text, 14, width=inner - 28,
                         color=NSColor.alternateSelectedControlTextColor() if index == selected else None)
            rows.append(((row, number, body, index == selected), 6))
        if hint:
            rows.append((label(hint, 11, color=NSColor.secondaryLabelColor()), PADDING))
        # Sizes: every label at its fitting size, the panel as wide as its widest line.
        widest, heights = (MIN_WIDTH if items or title else 0), []
        for row, x in rows:
            if isinstance(row, tuple):
                _, number, body, _ = row
                size = body.fittingSize()
                widest = max(widest, size.width + 28 + 2 * PADDING)
                heights.append(max(size.height, 18) + 8)
            else:
                size = row.fittingSize()
                widest = max(widest, size.width + 2 * PADDING)
                heights.append(size.height)
        width = min(WIDTH, widest)
        height = PADDING * 2 + sum(heights) + ROW_GAP * max(0, len(rows) - 1)
        y = height - PADDING
        for (row, x), h in zip(rows, heights):
            y -= h
            if isinstance(row, tuple):
                view, number, body, chosen = row
                view.setFrame_(NSMakeRect(6, y, width - 12, h))
                if chosen:
                    view.setWantsLayer_(True)
                    view.layer().setCornerRadius_(6)
                    view.layer().setBackgroundColor_(NSColor.selectedContentBackgroundColor().CGColor())
                number.setFrame_(NSMakeRect(PADDING - 6, (h - number.fittingSize().height) / 2,
                                            20, number.fittingSize().height))
                body.setFrame_(NSMakeRect(PADDING - 6 + 22, 4, width - 12 - PADDING - 22, h - 8))
                view.addSubview_(number)
                view.addSubview_(body)
                self.effect.addSubview_(view)
            else:
                row.setFrame_(NSMakeRect(x, y, width - 2 * PADDING, h))
                self.effect.addSubview_(row)
            y -= ROW_GAP
        (cx, cy), (cw, ch) = rect
        frame = NSMakeRect(cx, cy - height - 6, width, height)  # below the caret's line
        screen = NSScreen.mainScreen().visibleFrame()
        if frame.origin.y < screen.origin.y:  # no room below: above the line
            frame.origin.y = cy + ch + 6
        frame.origin.x = max(screen.origin.x + 4, min(frame.origin.x, screen.origin.x + screen.size.width - width - 4))
        self.window.setFrame_display_(frame, True)
        self.window.invalidateShadow()  # the shadow follows the rounded mask, not the square window
        self.window.orderFrontRegardless()

    def hide(self):
        if self.window is not None:
            self.window.orderOut_(None)


class Overlay:
    """Continue's suggestion: grey text right after the caret, in the app's font, never typed."""

    def __init__(self):
        self.window = None

    def show(self, rect, text, font=None):
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
        self.field.setStringValue_(text)
        self.field.setFont_(font or NSFont.systemFontOfSize_(13))
        self.field.setTextColor_(NSColor.placeholderTextColor())
        size = self.field.fittingSize()
        (cx, cy), (cw, ch) = rect
        self.window.setFrame_display_(NSMakeRect(cx + cw, cy + (ch - size.height) / 2, size.width, size.height), True)
        self.window.orderFrontRegardless()

    def hide(self):
        if self.window is not None:
            self.window.orderOut_(None)
