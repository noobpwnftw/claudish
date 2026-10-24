# Claudish roadmap

The input method as the way you talk to machines: autocomplete while you type, a rewrite of what
you composed, and one-line instructions answered at the caret, in every app, with the model you
configure. An input method, not a chat app (owner, 2026-10-23). Each step must earn trust: typed
text is never lost, nothing lands without a key you pressed, local is the default, and latency
feels like typing. The design: [docs/design/design.md](docs/design/design.md); how a request is
answered: [docs/design/architecture.md](docs/design/architecture.md).

This is the maintainer's queue (`AGENT.md`): goals with stable IDs, reprioritized on evidence.

## Open

| ID | Status | Goal and acceptance | Depends on |
| --- | --- | --- | --- |
| G45 | active | **The visual pass.** Every native input method matches the design lab (`claudish/web/design.html`) state by state, on Windows, macOS and GNOME, light and dark. Accept: each platform's gallery shot of every lab state checked against the lab's mock; the sign-off checks in design.md (Windows at 150/200% and high contrast, macOS appearances, GNOME text scaling). | |
| G01 | active | **Native typing in real apps.** Typing, taking a result, focus changes, shortcuts, secure fields, Unicode and service failure, on all three platforms. Accept: the desktop rigs (X11, GNOME Wayland, Windows Notepad/Edge/Terminal, macOS TextEdit/Terminal) green; reproduced bugs fixed with a rig check. | |
| G37 | active (internal beta) | **Install like any app.** Signed packages, a first run that explains itself, an obvious pause; until then the rigs are the beta. | G06 |
| G41 | active | **See what was sent.** `claudish recent` shows the last requests (done); next: the same from the panel's hosted mark. | |
| G02 | active | **A clean checkout is easy to try:** fresh-environment setup and model download verified; quick starts, troubleshooting and uninstall per OS. | |
| G47 | queued | **Configurable compose keys.** `keys.summon` (Enter, or Shift+Enter with Enter keeping your words), read by the shared state, so every adapter, the panel's footer, the demo, the lab and the docs follow; a toggle in G52 (the owner, 2026-10-24: configurable, not polled). Accept: unit tests for both; the panel's words follow. Also the mode switch key (Shift tap, Caps Lock, a chord). | G52 |
| G52 | queued | **A basic OS-native settings UI** with the toggles (the summon key, the mode key, the backend), reached from the taskbar, menu bar or top bar menu; it writes `config.json`, never a key. Accept: on each platform a toggle changes the behaviour without a restart; a rig flips one. | |
| G51 | queued | **Replace the instruction a focus change left in the text** when a draft is taken on return (round 6, 5/7), where it still sits right before the caret (IBus delete_surrounding_text, a TSF range, IMK's replacement range); else insert at the caret. Accept: a rig on each platform leaves, returns, takes a draft, and the instruction is gone. | |
| G50 | queued | **Per-app input profiles:** how cd_AI behaves in an app (bundle id, process, window class; next to G38's bindings). First: continue's Tab in macOS Terminal (the suggestion is not marked text, so Terminal keeps Tab). | G38 |
| G53 | active | **Choose the models carefully** (owner, 2026-10-24: no hunches): native and in-browser candidates (Gemma 4, Qwen3.5, LFM2.5, Gemma 3, Qwen2.5) on rewrite, continue and instruct. Judges calibrated on the hand labels, two families, disagreements read; a template per model chosen on a dev split, scored on a held-out split; latency where each runs (llama-server on the GB10, wllama in Chromium). Accept: a reproducible report in `benchmarks/` with raw outputs and settings; the defaults follow it. | |
| G21 | queued | **A small, purpose-trained Claudish model** that runs in the browser and does continue extremely well (ProgramAsWeights' "compile by training" recipe: generated pairs, a small model, the fidelity evaluation as the gate). | |
| G48 | queued (debatable) | **How much context continue gets,** measured, not assumed: completions with and without each kind of context, for latency and quality. | G21 |
| G32 | queued | **Remove continue's workarounds for model weakness** (the quoting frame, echo stripping, `parroted()`) once a model does continue well. | G21 |
| G49 | on demand | **Writing as you do:** if users ask, solved in the model (tuned on your writing, or your examples as context), not a habit store in Claudish. | G21, G48 |
| G46 | tabled | **Selected text into the buffer**, to recover words a focus change committed. | |
| G04 | queued | **Shareable demo material:** an accurate recording and launch text from the working product (new public posts need the owner's OK). | |
| G06 | queued | **Release readiness:** packaging, model licensing, versioning, CI artifacts, install and rollback, as a checklist with evidence. | |
| G30 | queued | **Auto-update:** `claudish update` fetches a signed release, shows what changes, and keeps the previous version to roll back to. | G06 |

## Done

| ID | What | Evidence |
| --- | --- | --- |
| G03, G12 | Fidelity evaluation (names, numbers, negation, facts) and a local judge for meaning flips | `benchmarks/evaluate.py`, gate: 38/41 |
| G05 | Contributor path | CONTRIBUTING.md, docs/development.md |
| G07 | Modifier characters stay in the composition; shortcuts commit and pass | unit tests, rigs |
| G08 | CI runs the IBus smoke and the PIME contract on all three OSes | `.github/workflows` |
| G09, G15, G28 | Continue (autocomplete), rewrite, instruct, and the model's own questions | rigs on all platforms |
| G10, G20, G38 | Context providers, supported text boxes, bindings routing an app to a profile | docs/configuration.md |
| G11, G13, G14 | Backends are configuration; one config with profiles; the house style is the model's | docs/configuration.md |
| G17, G43 | One request, one answer: one loop with tools, for local models and Claude | docs/design/architecture.md |
| G18, G27, G39, G44 | Agent sessions at the caret, drafts, handoff to a helper, follow-ups | live Claude Code runs, rigs |
| G19, G22–G25 | Onboarding, `doctor`, `service`, `mcp import`, `setup` | docs/install.md |
| G26 | A picture of the window as context (F8) | rigs |
| G29 | GNOME on Wayland, with a Shell extension drawing the panel | `tests/desktop/linux-gnome`: 13/13 |
| G31, G42 | The demo is an input method on the kit; the home page | claudish.io |
| G33, G34 | The key design, settled in six review rounds | docs/design/design.md, docs/research/ |
| G35 | Context from apps without MCP: terminals through accessibility | rigs on all platforms |
| G36 | A private local API (a per-run token) | unit tests |
| G16, G40 | Dropped: `claudish fix` (replaced by G35); the key poll (decided; the rest is G47) | |
