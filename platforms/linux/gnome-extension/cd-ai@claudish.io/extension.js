// cd_AI's panel and suggestion in GNOME Shell (docs/design/visual.md; the design lab's GNOME mock,
// claudish/web/design.html#gnome). The IBus engine (platforms/linux/engine.py) publishes what to
// show on the session bus (io.claudish.Screen: the panel as Composition.panel() describes it,
// continue's suggestion, the mode switch); this draws it at the IBus cursor, on X11 and Wayland
// alike. While it owns io.claudish.Shell the engine leaves IBus's own popup empty.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as IBusManager from 'resource:///org/gnome/shell/misc/ibusManager.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const GAP = 6;  // between the caret's line and the panel
const CARET_GAP = 5;  // between the caret and the suggestion

// A tile or a mark: its glyph centred in a fixed square (a sized label keeps its text top-left).
function mark(text, styleClass) {
    return new St.Bin({style_class: styleClass, y_align: Clutter.ActorAlign.CENTER,
        child: new St.Label({text, x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER,
            x_expand: true, y_expand: true})});
}

function label(text, styleClass, wrap = false) {
    const widget = new St.Label({text, style_class: styleClass, y_align: Clutter.ActorAlign.CENTER});
    if (wrap) {
        widget.clutter_text.line_wrap = true;
        widget.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        widget.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    }
    return widget;
}

export default class CdAiExtension extends Extension {
    enable() {
        this._cursor = {x: 0, y: 0, width: 0, height: 0};
        this._panel = new St.BoxLayout({vertical: true, style_class: 'cd-panel', visible: false});
        this._ghost = new St.Label({style_class: 'cd-ghost', visible: false});
        this._toast = new St.BoxLayout({vertical: true, style_class: 'cd-panel', visible: false});
        for (const actor of [this._panel, this._ghost, this._toast])
            Main.layoutManager.addTopChrome(actor, {affectsInputRegion: false});
        this._ibus = IBusManager.getIBusManager();
        this._cursorId = this._ibus.connect('set-cursor-location', (manager, rect) => {
            this._cursor = rect;
            this._place();
        });
        this._signal = Gio.DBus.session.signal_subscribe(null, 'io.claudish.Screen', 'Changed',
            '/io/claudish/Screen', null, Gio.DBusSignalFlags.NONE,
            (connection, sender, path, iface, name, parameters) => this._show(parameters.deep_unpack()[0]));
        this._name = Gio.bus_own_name(Gio.BusType.SESSION, 'io.claudish.Shell', Gio.BusNameOwnerFlags.NONE,
            null, null, null);
    }

    disable() {
        Gio.bus_unown_name(this._name);
        Gio.DBus.session.signal_unsubscribe(this._signal);
        this._ibus.disconnect(this._cursorId);
        if (this._toastTimeout)
            GLib.source_remove(this._toastTimeout);
        for (const actor of [this._panel, this._ghost, this._toast]) {
            Main.layoutManager.removeChrome(actor);
            actor.destroy();
        }
        this._panel = this._ghost = this._toast = this._ibus = this._toastTimeout = null;
    }

    _show(json) {
        let screen;
        try {
            screen = JSON.parse(json);
        } catch (e) {
            return;
        }
        this._fill(this._panel, screen.panel);
        if (screen.panel && !screen.toast)
            this._toast.visible = false;  // a panel replaces a toast at the caret
        this._ghost.visible = Boolean(screen.ghost);
        if (screen.ghost) {
            // cd_AI's own grey text, in the UI font at the caret's height.
            this._ghost.text = screen.ghost;
            this._ghost.style = `font-size: ${Math.max(11, Math.round(this._cursor.height / 1.25))}px;`;
        }
        if (screen.toast) {
            this._fill(this._toast, screen.toast);
            if (this._toastTimeout)
                GLib.source_remove(this._toastTimeout);
            this._toastTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
                this._toast.visible = false;
                this._toastTimeout = null;
                return GLib.SOURCE_REMOVE;
            });
        }
        this._place();
    }

    // The panel's anatomy: an optional header (a small label, then the content as is), the rows
    // (the highlighted one a neutral fill with the accent bar and its own Enter key; every row keeps
    // that key's column), and one footer (the tile or a warning mark, what is happening, each key
    // with its verb, the free words, a hosted model's name at the end).
    _fill(box, panel) {
        box.destroy_all_children();
        box.visible = Boolean(panel);
        if (!panel)
            return;
        const thread = panel.thread || [];
        box.style_class = 'cd-panel' + (panel.rows.length || panel.body || thread.length ? '' : ' cd-bare')
            + (panel.replying ? ' cd-replying' : '');
        // The exchange so far: your earlier turns as context, one line each, muted, a rule beside.
        for (const turn of thread) {
            // Your words at full size and colour, underlined as at the caret; the label muted.
            const line = new St.BoxLayout({style_class: 'cd-turn'});
            const words = label('', 'cd-turn-text');
            words.clutter_text.ellipsize = Pango.EllipsizeMode.MIDDLE;
            words.clutter_text.set_markup(`<b><span size="smaller" fgalpha="70%">${GLib.markup_escape_text(turn.label, -1)}</span></b>  ` +
                `<u>${GLib.markup_escape_text(turn.body, -1)}</u>`);
            line.add_child(words);
            box.add_child(line);
        }
        if (panel.body) {
            const head = new St.BoxLayout({vertical: true, style_class: 'cd-head'});
            if (panel.label)
                head.add_child(label(panel.label, 'cd-label', true));
            head.add_child(label(panel.body, panel.code ? 'cd-body cd-code' : 'cd-body', true));
            box.add_child(head);
        }
        const takes = panel.on >= 0;
        panel.rows.forEach((row, index) => {
            const on = index === panel.on;
            const line = new St.BoxLayout({style_class: on ? 'cd-row cd-on' : 'cd-row'});
            line.add_child(new St.Widget({style_class: on ? 'cd-bar' : 'cd-bar cd-off', y_expand: true}));
            if (row.key)  // choices are not numbered: digits are text, as Space is
                line.add_child(label(row.key, 'cd-key'));
            const text = label('', 'cd-text', true);
            const words = GLib.markup_escape_text(row.text, -1);
            text.clutter_text.set_markup(row.legend
                ? `${words}<span fgalpha="62%"> — ${GLib.markup_escape_text(row.legend, -1)}</span>` : words);
            text.x_expand = true;
            line.add_child(text);
            if (takes) {  // the trailing column: the highlighted row's Enter
                // Tab takes a draft; lit after Enter on the model's text (panel.nudge)
                const take = label(on ? panel.take || 'Enter' : '', on ? (panel.nudge ? 'cd-cap cd-lit' : 'cd-cap') : 'cd-take');
                line.add_child(take);
            }
            box.add_child(line);
        });
        const foot = new St.BoxLayout({style_class: 'cd-foot'});
        if (panel.tile === 'warn')
            foot.add_child(mark('!', 'cd-warn'));
        else
            foot.add_child(mark(panel.tile === 'cd' ? 'cd' : 'AI', panel.tile === 'cd' ? 'cd-tile cd-neutral' : 'cd-tile'));
        if (panel.status) {
            if (panel.busy) {
                const spinner = new St.Icon({icon_name: 'process-working-symbolic', style_class: 'cd-spinner'});
                spinner.set_pivot_point(0.5, 0.5);
                spinner.ease({rotation_angle_z: 360, duration: 1000, repeatCount: -1, mode: Clutter.AnimationMode.LINEAR});
                foot.add_child(spinner);
            }
            foot.add_child(label(panel.status, 'cd-status'));
        }
        if (panel.failed)
            foot.add_child(label(panel.failed, 'cd-failed'));
        for (const [key, verb] of panel.foot) {
            const hint = new St.BoxLayout({style_class: 'cd-hint'});
            hint.add_child(label(key, panel.nudge && key === (panel.take || 'Enter') ? 'cd-cap cd-lit' : 'cd-cap'));
            hint.add_child(label(verb, 'cd-verb'));
            foot.add_child(hint);
        }
        if (panel.tail)
            foot.add_child(label(panel.tail, 'cd-verb'));
        if (panel.mark) {
            foot.add_child(new St.Widget({x_expand: true}));
            foot.add_child(label(panel.mark, 'cd-verb'));
        }
        box.add_child(foot);
    }

    // Under the caret's line, the content starting at the caret (IBus reports only the caret, so
    // every platform anchors there); the suggestion right after the caret. Clamped to the monitor.
    _place() {
        const {x, y, width, height} = this._cursor;
        const monitor = Main.layoutManager.findMonitorForActor(this._panel) || Main.layoutManager.primaryMonitor;
        for (const box of [this._panel, this._toast]) {
            if (!box.visible) {
                box._opened = null;
                continue;
            }
            const [, natural] = box.get_preferred_width(-1);
            const [, tall] = box.get_preferred_height(natural);
            const inset = box.get_theme_node().get_padding(St.Side.LEFT) + 10;
            let left = Math.round(x + width - inset), top = Math.round(y + height + GAP);
            // It opens under the caret and stays where it opened while it is open on that line and the
            // caret is at or right of it (when the text leaves, it moves to the caret).
            if (box._opened && box._opened.line === y && left >= box._opened.left)
                left = box._opened.left;
            box._opened = {left, line: y};
            left = Math.max(monitor.x + 4, Math.min(left, monitor.x + monitor.width - natural - 4));
            if (top + tall > monitor.y + monitor.height)
                top = Math.round(y - tall - GAP);  // no room below: above the line
            box.set_position(left, top);
        }
        if (this._ghost.visible) {
            const [, tall] = this._ghost.get_preferred_height(-1);
            // Just past the caret's line (the reported x is a few pixels left of the drawn caret):
            // the suggestion never covers the space you typed.
            this._ghost.set_position(Math.round(x + Math.max(width, 2) + CARET_GAP), Math.round(y + (height - tall) / 2));
        }
    }
}
