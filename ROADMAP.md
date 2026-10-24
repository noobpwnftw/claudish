# Claudish roadmap

An input method, not a chat app: continue while you type, a rewrite of what you composed, and
one-line instructions answered at the caret, in every app, with the model you configure. Design:
[docs/design/design.md](docs/design/design.md); architecture:
[docs/design/architecture.md](docs/design/architecture.md). What is done is in the
[changelog](CHANGELOG.md) and git history.

## Now

| ID | Goal | Done when |
| --- | --- | --- |
| G01 | **Works the same on all three platforms** | Install, restart, type, update and uninstall pass on macOS, Windows and Linux |
| G45 | **The panels match the design lab**, state by state | Each platform checked in both themes |
| G06 | **Release 0.1.0** | Published with the macOS package and the Windows installer ([docs/release.md](docs/release.md) when it lands) |

## Next

| ID | Goal |
| --- | --- |
| G47 | Configurable compose keys (`keys.summon`), read by the shared state |
| G50 | Per-app input behavior beside bindings; first, continue's Tab in macOS Terminal |
| G60 | fcitx5 on Linux |
| G30 | `claudish update`, keeping the previous version to roll back to |

## Later or on demand

A small purpose-trained model for continue (G21, after G53 found nothing under 1B usable), then the
continue measurements and workarounds that depend on it (G48, G32, G49); a demo share card (G57);
tone and templates directly on a binding (G59); selected text back into the buffer (G46).
