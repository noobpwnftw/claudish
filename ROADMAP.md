# Claudish roadmap

An input method, not a chat app: continue while you type, a rewrite of what you composed, and
one-line instructions answered at the caret, in every app, with the model you configure. Design:
[docs/design/design.md](docs/design/design.md); architecture:
[docs/design/architecture.md](docs/design/architecture.md). What is done is in the
[changelog](CHANGELOG.md) and git history.

## Now

0.2.0 is out (https://github.com/noobpwnftw/claudish/releases/latest). From here the slop
experience comes first: `ok`, Tab, a paragraph of strategic momentum, Tab. The ask workflow
(instructions, tools, approvals, handoffs) is for experts; it gets fixes for the bugs they report.

| ID | Goal | Done when |
| --- | --- | --- |
| G65 | **Slop quality per backend** | Every tone's rewrites measured with `benchmarks/` on the backends people use (Claude Code, Codex, an API key, Gemma 4), and the templates changed only where the numbers improve |
| G67 | **The demo's slop** | The browser model's rewrites and continue suggestions read as the product does, on the samples and on free typing |
| G63 | **Install → model → first accepted rewrite** | A new user gets a real rewrite in Settings, then accepts `ok` with Tab in a native editor, on each published package |
| G45 | **The panels match the design lab**, state by state | Each platform checked in both themes |

## Next

| ID | Goal |
| --- | --- |
| G64 | A drafts or rewrite panel taller than the screen: cap its height on every platform (rows scroll), as the lab draws it |
| G50 | Continue's Tab in macOS Terminal: follow the platform's input-method behavior; keep the limitation documented until verified |
| G60 | fcitx5 on Linux |
| G30 | `claudish update`, keeping the previous version to roll back to |
| G69 | Structured output: each mode asks for a declared shape (a rewrite, versions, a part's replacement) and reads it back as data, through each backend's own schema support; the model-specific clean-up and parsing go, and the quirks that remain live in one declared place |

## Later or on demand

A small purpose-trained model for continue (G21, after G53 found nothing under 1B usable), then the
continue measurements and workarounds that depend on it (G48, G32, G49); a demo share card (G57);
tone and templates directly on a binding (G59).

Not planned: rewriting a selection with a hotkey. That is the ground of selection tools (Grammarly,
ClipSlop, AI Shortcuts and others); cd_AI works on what you compose at the caret, and either can run
beside it.

For further consideration (G68): knowing which field the caret is in, such as a browser's address
bar. macOS gives an input method no field type, and browsers do not all mark their address bars as
URL fields on Linux or Windows, so it would take per-app identification, which the invariants rule
out. Today such a field is an ordinary text field to the model.

The browser demo keeps Qwen2.5 0.5B, selected from the candidates that fit browser constraints.
Revisit that choice only when a candidate improves the measured size, loading time, speed and
quality tradeoff. Broader native-model scores alone are not a reason to replace it.
