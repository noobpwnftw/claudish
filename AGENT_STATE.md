# Maintainer handoff

Checkpoint 2026-10-25 (late), `main` at `2f3fbb3`. An interactive session on the Spark; no 24/7 runner.

## Settled

The design is [docs/design/design.md](docs/design/design.md); the request/answer architecture is
[docs/design/architecture.md](docs/design/architecture.md); how it was reached is in
docs/research/. The web is the design: `claudish/web/kit.css`/`kit.js` and the lab
(`design.html`) are the reference, `claudish/composition.py` produces every panel description, and
the natives match the lab state by state. Owner direction: no per-platform special cases; the CJK
input-method reviewers weigh most on keys; get the thing to work before anything else; user-facing
copy says what things do and nothing more.

## Current task

Owner (2026-10-25): carry on autonomously; everything must work in practice and stay installed;
configs and docs must work as written. The six-reviewer findings are fixed on main, except Windows
(a fork is fixing and verifying them on the VM, branch `agent/windows-review`). A second fork runs
every documented config and command for real (branch `agent/config-practice`, its own worktree).
Done today besides: bindings rethought (a binding routes and adds standing reference; per-request
context comes with the request) and a routed binding's context fixed; "voice" renamed "tone"; the
README opens with a real recording (docs/cd_AI.gif); a bug report form; hosted labels and every
narrative gone. Mac VM: build, install, restart, "ok" + Tab verified after the macOS fixes.

Next: the Windows and config forks' results; a Mac persistence check (restart, still enabled and
running); then the established-review round with the thefuck calibration.

## Release 0.1.0

Not released. One blocker: a rewrite through Claude with a valid Anthropic API key, which only the
owner can run (docs/release.md on branch `agent/release-0.1.0`, rebuilt on main at `00caebe`
with the download-first README and site and the release notes; rebase it again before release).

## Checks (owner, 2026-10-24)

The gate is `python scripts/check.py`, every step under 5 s (unit tests run one process per file:
about 1.5 s, 2.7 s with the `[claude,mcp]` extras). Real typing is checked by hand. Remote CI is
paused by the owner. Merge rule: `check.py` passes on the merged result; main is fast-forward only.

## Running (owned)

- llama-server with Gemma 4 E4B on the Spark, bound to the network for the Mac and Windows VMs'
  "Another model API" (`http://10.0.0.249:18790`), pid 689074 in the scratchpad's gemma-lan.pid.
  Stop it when the hand tests are done.

## Environment and owned resources

- Mac VM: `ssh -i ~/.ssh/claudish_mac_vm claudish@10.0.0.251`, repo ~/claudish (sync by tar over
  ssh). Build `.tools/macos-build-venv/bin/python platforms/macos/build.py`, then
  `platforms/macos/package.py` and install the .pkg; auto-login, so a restart is the logout. Never
  The VNC login can click (owner, 2026-10-25): an Allow dialog is ours to click.
- Windows 11 ARM64 VM (dockur container): Claudish's patched PIME is built there with VS Build Tools
  into C:\PIME-build; `platforms/windows/package.py` builds cd_AI-setup.exe over it. Job runner and
  helpers are in the session scratchpad's win/ folder.
- Models in `models/` (untracked): Qwen2.5 0.5B and SmolLM2 135M, Gemma 4 E2B/E4B/12B/26B-A4B (QAT
  Q4_0; the 26B is the judge), Qwen3-30B-A3B (tool and agent checks), Qwen2.5-VL-3B with its mmproj.
  Extras venv `.tools/claude-venv`; browser venv `.tools/browser-venv`; CUDA llama.cpp in
  `.tools/build`.
- claudish.io: site/ plus the static demo at /demo/, deployed by .github/workflows/pages.yml on
  every push to main.
- Waiting on the owner: deleting old remote branches; publishing the release.
