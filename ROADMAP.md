# Claudish roadmap

An input method, not a chat app: continue while you type, a rewrite of what you composed, and
one-line instructions answered at the caret, in every app, with the model you configure. Design:
[docs/design/design.md](docs/design/design.md); architecture:
[docs/design/architecture.md](docs/design/architecture.md). What is done is in the
[changelog](CHANGELOG.md) and git history.

## Now

| ID | Goal | Done when |
| --- | --- | --- |
| G63 | **Install → model → first accepted rewrite** | A new user chooses a subscription or API, gets a real rewrite in Settings, then accepts `ok` with Tab in a native editor after login/restart; repeat on each installed package |
| G06 | **Downloadable 0.1.0** | Release candidates built from reviewed source, installed and exercised from their downloads; the owner approves publishing the macOS package and Windows installer |
| G01 | **Works the same on all three platforms** | Install, restart, type, update and uninstall pass on macOS, Windows and Linux |
| G45 | **The panels match the design lab**, state by state | Each platform checked in both themes |

Candidates from `926e0bc` (2026-10-25): the macOS package installed and hand-tested by the owner
(rewrites, drafts, answers, a session handoff, MCP approvals; Gemma 4 and Claude Code), the Windows
ARM64 installer installed by a standard account with its service at login. Linux: the Docker rig
and GNOME Shell's drawing of every panel. Still open for G63: a logged-in subscription on Windows,
Windows x64, a real Linux desktop. Evidence:
[docs/development.md](docs/development.md#current-evidence-and-next-checks).

For G06: `agent/release-0.1.0` is one commit on main with these candidates' hashes. Waiting on the
owner: the funded Anthropic-key check, browser-download installs, then publishing.

## Next

| ID | Goal |
| --- | --- |
| G64 | A drafts or rewrite panel taller than the screen: cap its height on every platform (rows scroll), as the lab draws it |
| G50 | Continue's Tab in macOS Terminal: follow the platform's input-method behavior; keep the limitation documented until verified |
| G60 | fcitx5 on Linux |
| G30 | `claudish update`, keeping the previous version to roll back to |

## Later or on demand

A small purpose-trained model for continue (G21, after G53 found nothing under 1B usable), then the
continue measurements and workarounds that depend on it (G48, G32, G49); a demo share card (G57);
tone and templates directly on a binding (G59); selected text back into the buffer (G46).

The browser demo keeps Qwen2.5 0.5B, selected from the candidates that fit browser constraints.
Revisit that choice only when a candidate improves the measured size, loading time, speed and
quality tradeoff. Broader native-model scores alone are not a reason to replace it.
