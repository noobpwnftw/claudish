# Maintainer handoff

Checkpoint 2026-10-24, `main` at `1218e2a`: templates are data, cd_AI starts in compose, the
panel anchors at the composition's start; G53 (choosing models) is running. An interactive session
on the Spark; no 24/7 runner.

## Settled

The design is [docs/design/design.md](docs/design/design.md); the request/answer architecture is
[docs/design/architecture.md](docs/design/architecture.md); how it was reached is in
docs/research/. The web is the design: `claudish/web/kit.css`/`kit.js` and the lab
(`design.html`) are the reference, `claudish/composition.py` produces every panel description, and
the natives match the lab state by state. Owner direction: think at the architecture level, no
per-platform duct tape; the CJK input-method reviewers weigh most on keys.

## Current task

G53, choosing the models by a careful evaluation (owner: no hunches; English only, cd_AI is the
English input method). Owner's leaning, pending the results: compose by default (done) with a
frontier model behind it, taking the latency. Runs in the scratchpad (not in the repo): 14 models
(13 local + Claude Haiku via `claude -p`) x 3 template sets on 80 rewrite and 86 continue cases;
judged by Gemma 4 26B + Qwen2.5-14B (rewrite, 94% agreement with hand labels when both must pass)
and Gemma 4 26B + Qwen3-30B (continue, 91% with the checks); `benchmarks/compare.py` picks a
template per model on the dev half and scores the test half. Latency: GB10, CPU-only 4 threads,
and wllama in Chromium (`benchmarks/browser_latency.py`). Next: the report in benchmarks/, then
the defaults follow it.

## Verified (latest)

- `1218e2a`: gate `check.py --model` 10/10, CI 5/5; desktop rigs Linux 41/41, GNOME 16/16 (the
  anchor checks), Windows 15/15 + terminal 4/4, macOS 11/11.
- Templates refactor (`6b53191`): every prompt byte-identical to before, across tones, modes and
  box kinds.

## Open, waiting, or parked

- Decided: the summon key is a toggle in a native settings UI (G47, G52). Dropped: keeping the panel inside the app's window.
- Parked: the Claude API tool loop against the live API (needs a key); G30 (needs releases); G21
  (a trained model); an upstream PIME proposal (a public post: owner's OK).
- Known: Linux GTK reports no selection (Qt does); macOS Terminal keeps Tab from continue's
  suggestion (G50).

## Environment and owned resources

- Mac VM: `ssh -i ~/.ssh/claudish_mac_vm claudish@10.0.0.251`, repo ~/claudish (sync by tar over
  ssh; `git stash` holds older VM-local edits). Build `.tools/macos-build-venv/bin/python
  platforms/macos/build.py`, install in place `tests/desktop/macos/driver.py --reinstall`. The
  service must run on the venv's Python (`.tools/macos-build-venv/bin/python -m claudish serve
  --backend rules`): system Python has no AppKit, so it cannot read a terminal's screen. Never
  click the owner's consent dialogs or write AppleEnabledInputSources; warn before a rebuild that
  needs an Allow or a relogin. Gallery: `tests/desktop/macos/gallery.sh` with vncdotool.
- Windows VM `claudish-windows` (container; `tests/desktop/windows/vm.sh start|stop`): Claudish's
  patched PIME, built there with VS Build Tools. Loop: `vm.sh sync` (the last commit), `vm.sh pime`
  and `vm.sh run jobs/build-pime.ps1 900` when the patches change, `vm.sh run jobs/deploy.ps1
  300`, `vm.sh run jobs/typing.ps1 400`; `gallery.sh OUT`; `vmscreen.sh OUT.png`.
- Models in `models/` (untracked): Qwen 0.5B/1.5B/14B, Qwen3-30B-A3B, Qwen2.5-VL-3B, Gemma 4
  (E2B, E4B, 12B, 26B-A4B; QAT Q4_0, Apache-2.0; thinking off with `--chat-template-kwargs
  '{"enable_thinking":false}'`), Gemma 3 270M/1B, Qwen3.5 0.8B/2B, LFM2.5 350M/1.2B. Extras venv
  `.tools/claude-venv`; browser venv `.tools/browser-venv`.
- claudish.io: site/ plus the static demo at /demo/, deployed by .github/workflows/pages.yml on
  every push to main.
- Merge rule: clean `check.py --model` on the merged result, a `ci/*` run for Windows/macOS
  adapters or packaging (check the jobs on the actual head SHA); main is fast-forward only.
