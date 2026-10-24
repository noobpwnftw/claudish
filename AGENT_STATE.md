# Handoff

2026-10-25, `main` after `3e316cf`.

## Now

- G64: a fork runs every documented config and command for real (branch `agent/config-practice`,
  its own worktree); it also has two install.sh findings (no `claudish` on PATH after install.sh;
  doctor's service fix names a source checkout's commands).

Verified 2026-10-25, each in one run:
- Windows review fixes on the ARM64 VM (`376eafb`).
- Windows stays installed: install, restart, update over it, restart; the service, its task, the
  input source and both launchers are there each time; "ok" + Tab Tab rewrites in Notepad.
- Mac: build, install, restart, "ok" + Tab in TextEdit; still enabled and serving after a restart.
- Linux: install.sh in a clean Ubuntu 24.04 container; setup --yes and doctor name the next steps.

## Next

The config fork's result; then the established-review round, with thefuck (nvbn/thefuck) as the
bar: only what a first visitor would notice as unfinished counts.

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
- /home/nooby/Downloads/claudish is the main checkout (on `main`); forks use their own worktrees.
