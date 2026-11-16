# cd_AI 0.4.8

- Accents: an accent left waiting on its dead key (U.S. International's closing quote) goes in
  before Enter, and before Tab and Shift+Enter while you compose, on Linux, macOS and Windows: the
  rewrite or instruction has the quote you saw.
- Continue: a suggestion after any line break (Word's, a Qt app's Shift+Enter) or a no-break space
  starts without a space; no suggestion right after £, €, ¥ or an en dash, as after $ and a hyphen;
  a model that repeats your text across paragraphs (WordPad, Word) is not inserted twice. A preview
  is never cut inside an emoji or a flag, and macOS takes a selection of emoji up to the same limit
  as the other platforms.
- Settings and `claudish doctor`: Claude Code or Codex signed out stays said (log in) after a
  rewrite it refused, rather than turning ready. A config file that does not read is said as that,
  with cd_AI keeping the settings it had until it does. The first-run settings say where to add
  Claudish on Linux.
- Linux desktops other than GNOME: `claudish doctor` accepts IBus reached through Wayland or XIM,
  tells Sway and Hyprland to set the IBus modules, says when a session does not read
  `environment.d` (use `--system`), and checks that Claudish is among IBus's input methods; the
  install and docs say to add it in IBus Preferences there. `claudish setup` reports doctor's own
  failure rather than registering again. The site's install-by-hand line keeps the system's
  packages on Linux, so instructions in a terminal read its last lines.
- Windows: the installer is 7.5 MB smaller.
- macOS: `claudish doctor` names Text Input and Claudish — Compose, as System Settings does.
