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
| G61 | active | **One installer per OS** (owner, 2026-10-24, after the [install poll](docs/research/2026-10-24-install-poll.md)): a prebuilt bundle with its own Python; it registers and enables the input method (no adding it by hand, no logout) and starts the service. macOS: an ad-hoc signed `cd_AI.pkg` (no Developer ID), the site's Download button first with a three-frame picture of Settings > Open Anyway, a `curl` one-liner second (no Gatekeeper prompt). Windows: a per-machine Inno Setup installer with Claudish's PIME, also through winget (no SmartScreen). Linux: the install script over today's setup. Accept: on a clean VM per platform, install, the system's own Allow, Tab lands a rewrite; nothing else. | G63 |
| G62 | queued | **The settings window** (G52's first version; owner: a window, not a wizard): "Settings…" in the input menu, opened once at the end of install: the key (Keychain on macOS, the user's profile on Windows, a 0600 file on Linux; never config.json), the voice, "use a local model instead". Accept: on each platform, a fresh install reaches a rewrite through the window alone. | G61 |
| G63 | queued | **Release gates** (install poll): the input method falls back to plain typing when the service is down, slow or offline (a rig with the service stopped and the network off); a clean-VM install-and-Tab test per platform; Windows Defender on a clean Windows 11 (submit builds as false positives in advance). | |
| G45 | active | **The visual pass.** Every native input method matches the design lab (`claudish/web/design.html`) state by state, on Windows, macOS and GNOME, light and dark. Accept (install poll, user-level): the panel never clips or covers the caret and reads as native in light and dark at 1x and 2x on each platform, with one check at 150% and one in high contrast; the settings window looks like a system pane. Pixel-matching beyond that stops. | |
| G01 | active | **Native typing in real apps.** Typing, taking a result, focus changes, shortcuts, secure fields, Unicode and service failure, on all three platforms. Accept: the desktop rigs (X11, GNOME Wayland, Windows Notepad/Edge/Terminal, macOS TextEdit/Terminal) green; reproduced bugs fixed with a rig check. | |
| G41 | active | **See what was sent.** `claudish recent` shows the last requests (done); next: the same from the panel's hosted mark. | |
| G02 | active | **A clean checkout is easy to try:** fresh-environment setup verified (no model ships: a key, or `--profile local`); quick starts, troubleshooting and uninstall per OS. | |
| G47 | queued | **Configurable compose keys.** `keys.summon` (Enter, or Shift+Enter with Enter keeping your words), read by the shared state, so every adapter, the panel's footer, the demo, the lab and the docs follow; a toggle in G62's settings window (the owner, 2026-10-24: configurable, not polled; the CJK habit, Enter commits your words, is the later setting the 2026-10-24 onboarding poll asked for). Swapping moves everything Enter does today with it (owner): answering a question's highlighted choice, refusing an approval with a reason, sending a reply, retrying an instruction; picking stays on ↑↓ and Tab. Accept: unit tests for both bindings across every state the lab draws; the panel's footer words follow. Also the mode switch key (Shift tap, Caps Lock, a chord). | G62 |
| G51 | queued | **Replace the instruction a focus change left in the text** when a draft is taken on return (round 6, 5/7), where it still sits right before the caret (IBus delete_surrounding_text, a TSF range, IMK's replacement range); else insert at the caret. Accept: a rig on each platform leaves, returns, takes a draft, and the instruction is gone. | |
| G50 | queued | **Per-app input profiles:** how cd_AI behaves in an app (bundle id, process, window class; next to G38's bindings). First: continue's Tab in macOS Terminal (the suggestion is not marked text, so Terminal keeps Tab). | G38 |
| G57 | tabled (owner, 2026-10-24: onboarding and visuals first) | **A share card in the demo** (onboarding poll): "you typed: ok → cd_AI: …" as an image with the wordmark, ready for Slack or X: the day-1 growth loop. | |
| G58 | tabled (owner, 2026-10-24: onboarding and visuals first) | **SECURITY.md** (onboarding poll): what leaves the machine per profile and mode (text, the box around the caret, context, a terminal's lines, a window picture), the token file and port, that redaction is a best effort, where `claudish recent` keeps records, and how to report a vulnerability. | |
| G59 | tabled (owner, 2026-10-24: onboarding and visuals first) | **Voices without friction** (onboarding poll): `"tone"` and `"templates"` directly on a binding; the service picks up edits to config.json and templates.json without a restart; `claudish rewrite --tone X "ok"` documented as the loop for writing a voice. | |
| G60 | tabled (owner, 2026-10-24: onboarding and visuals first) | **fcitx5 on Linux** (onboarding poll: CJK users' Rime runs there; IBus only is not stated today). First, say so in the install guide. | |
| G21 | reconsider (G53: nothing under 1B makes usable slop) | **A small, purpose-trained Claudish model** that runs in the browser and does continue extremely well (ProgramAsWeights' "compile by training" recipe: generated pairs, a small model, the fidelity evaluation as the gate). | |
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
| G37, G52 | Replaced by G61 (one installer per OS) and G62 (the settings window), after the install poll. | docs/research/2026-10-24-install-poll.md |
| G54 | **Slop is the default voice**, with named tones (salesman, critic, bard, proofread; "fix" renamed) that each guard the meaning; checked on Gemma 4 E4B (rewrite 71–80/80, continue 82–85/86). | `2061559` |
| G55 | **The local model is Gemma 4 E4B** (QAT Q4_0, pinned, SHA-256 verified, thinking off); the systemd test runs it end to end. | `85032ad` |
| G56 | **Onboarding as a funnel:** the README and homepage open with real slop and five voices; `claudish init` writes an editable templates.json, `claudish templates` prints what a profile ends up with; setup asks for a voice once; then the onboarding poll. | `2061559`, `84b106b`, docs/research/2026-10-24-onboarding-poll.md |
| G53 | **Choosing the models** (owner: no hunches): 14 candidates on the slop voice, judged by Gemma 4 26B (calibrated on hand labels: rewrite 92%, continue 86%, slop 90%), test half after dev-half template choice, latency on GPU, CPU alone and in the browser. Gemma 4 E4B/12B/26B make slop as well as anything tried, frontier included; nothing under 1B does. | `ff4876c`, benchmarks/README.md (Choosing the models) |
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
