# Handoff

2026-10-25, `main` after `3e316cf`.

## Now

- Windows review fixes: a fork on branch `agent/windows-review` (in /home/nooby/Downloads/claudish),
  verifying on the Windows VM.
- G64: a fork runs every documented config and command for real (branch `agent/config-practice`,
  its own worktree).
- Mac: build, install, restart, then "ok" + Tab, verified after the macOS fixes; cd_AI stays enabled
  and its service comes back after a restart.

## Next

The forks' results, then a Windows stays-installed run (update over an install, restart). Then the
established-review round, with thefuck (nvbn/thefuck) as the bar: only what a first visitor would
notice as unfinished counts.

## Release 0.1.0

Branch `agent/release-0.1.0`: download-first README and site, the Linux script pinned to v0.1.0,
release notes, docs/release.md. Rebase it before release. Blocked on the owner: a rewrite through
Claude with a valid Anthropic key.

## Running and where things are

- llama-server with Gemma 4 E4B on the Spark at `http://10.0.0.249:18790` (pid in
  scratchpad/gemma-lan.pid), the VMs' model API.
- Mac VM: `ssh -i ~/.ssh/claudish_mac_vm claudish@10.0.0.251`; scratchpad/mac_e2e.sh is the
  one-shot build, install, restart and type cycle (about 2 minutes); VNC can click.
- Windows 11 ARM64 VM: the job runner and helpers in scratchpad/win.
- Venvs: `.tools/claude-venv` (SDK extras), `.tools/browser-venv` (Playwright). Models in `models/`.
- Worktree /home/nooby/Downloads/claudish-main is the main session's (on `main`).
