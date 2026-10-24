# Maintainer handoff

Checkpoint 2026-10-24, `main` at `a372df3`. An interactive session on the Spark; no 24/7 runner.

## Settled

The design is [docs/design/design.md](docs/design/design.md); the request/answer architecture is
[docs/design/architecture.md](docs/design/architecture.md); how it was reached is in
docs/research/. The web is the design: `claudish/web/kit.css`/`kit.js` and the lab
(`design.html`) are the reference, `claudish/composition.py` produces every panel description, and
the natives match the lab state by state. Owner direction: think at the architecture level, no
per-platform duct tape; the CJK input-method reviewers weigh most on keys.

## Current task

G61, one installer per OS, then G62 (the settings window) and G63 (release gates), with G45 to its
user-level acceptance (docs/research/2026-10-24-install-poll.md). Owner: no Apple Developer ID; on
macOS the Download button (.pkg, ad-hoc signed; Open Anyway in Privacy & Security, measured on
26.6) first and a curl one-liner second; a settings window, not a wizard; avoid feature creep.
G57-G60 tabled.

## Verified (latest)

- G61 macOS (branch `agent/mac-package`): `platforms/macos/package.py` builds `cd_AI.pkg` (36 MB,
  ad-hoc, current-user domain, no password). On the VM, `installer -target CurrentUserHomeDirectory`
  over a running build: the postinstall stops the old build (as Squirrel's does), writes the starter
  config, loads the login service (the bundle's own `serve`; `/health` answers, Claude backend) and
  registers/enables/selects the input source; the rig then 12/12 in one run. A second service on a
  taken port now exits 0 without replacing the running one's token (it caused the rig's 403s), and
  launchd restarts only crashes. CI paused by the owner (Check workflow disabled) until G61-G63/G45. The key is in the Keychain (`claudish key`). Not yet: the GUI
  Installer path with Open Anyway (owner's hand test), publishing a release (needs the owner).
  Finder's desktop: macOS opens its own bottom input window for every IME (owner checked Pinyin);
  no special case.
- `ff4876c` (G53 report): gate `check.py --model` 10/10. `378ef93` (install steps): gate, CI 5/5,
  the systemd container test (setup --profile local end to end). `6f21847` (no model ships): gate,
  CI 5/5. `05ff8bb` (compose default): Linux 41/41, GNOME 13/13, Windows 15/15 + 4/4, macOS 11/11.
  `1218e2a` (panel anchors at the composition's start): GNOME 16/16, Windows 15/15, macOS 11/11.
- G53 (benchmarks/README.md, Choosing the models): slop rewrite Gemma 4 26B 95%, E4B 93%, 12B 93%,
  Qwen3-30B 83%, Claude Haiku 80%, E2B 61%, everything under 2B at most 44%; continue Qwen3-30B 96%,
  Gemma 12B 94%, E4B 91%, E2B 83%. CPU alone (4 threads): E2B 1.5 s, E4B 3–4 s, 0.5B 0.25 s.

## Open, waiting, or parked

- Decided: the summon key is a toggle in a native settings UI (G47, G52). Dropped: keeping the panel inside the app's window.
- Waiting on the owner: deleting 130 old remote branches on GitHub (merged long ago; deletion needs
  the owner's OK); the two unmerged local branches (agent/handoff: parked, superseded;
  agent/macos-typing: an experimental CI job, superseded by the Mac VM rig).
- Owned processes: the Mac VM runs `claudish serve --backend rules` for its rig (nohup, port 18765).
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
- Models in `models/` (untracked, 49 GB): Qwen2.5 0.5B and SmolLM2 135M (the gate's presets),
  Gemma 4 E2B/E4B/12B/26B-A4B (QAT Q4_0, Apache-2.0; thinking off with `--chat-template-kwargs
  '{"enable_thinking":false}'`; the 26B is the judge), Qwen3-30B-A3B (tool and agent checks),
  Qwen2.5-VL-3B with its mmproj (window pictures). Extras venv `.tools/claude-venv`; browser venv
  `.tools/browser-venv`; the CUDA llama.cpp build in `.tools/build`.
- claudish.io: site/ plus the static demo at /demo/, deployed by .github/workflows/pages.yml on
  every push to main.
- Merge rule: clean `check.py --model` on the merged result, a `ci/*` run for Windows/macOS
  adapters or packaging (check the jobs on the actual head SHA); main is fast-forward only.
