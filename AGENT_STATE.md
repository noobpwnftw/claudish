# Maintainer handoff

Checkpoint 2026-10-23 (late), `main` at `8a091ae`. An interactive session on the Spark; no 24/7 runner.

## Where things stand

- **Owner direction:** finish functionality and key designs before visuals; loop until only
  model training (G21) and UI polish remain. Claudish is an IME, not a chat app: turn-based
  autocomplete, one-line tasks, context between invocations. Models are placeholders until G21;
  Continue's model workarounds are duct tape (G32, remove after G21).
- **Key design (G33, done):** F7 is retired. A Shift tap switches continue (keys go straight in,
  Tab takes the suggestion) and compose (buffered). Compose: Tab rewrites in place (Tab again
  keeps), Enter instructs (drafts, 1–3 pick), Shift+Enter commits as is, Esc steps back then
  drops. Only letters and digits start a composition. A selection taken into compose goes back
  on Esc (never dropped). Same in all adapters, the demo, and the docs.
- **Text box description (G34):** every request carries app, field purpose, text before/after the
  caret; quiet in URL/email/number fields, nothing in password fields. Agents get the profile's
  MCP servers, policy and context, plus `claudish textbox-mcp`; editor context comes from F8
  pictures or MCP servers configured for Claudish (never Claude Code's own config/token).
- **Mode indicators:** IBus InputMode property (GNOME top bar C/AI, verified); PIME C/AI icon
  (taskbar screenshot verified); macOS one input source "cd_AI" with a template cd.tiff icon
  (multi-mode sources didn't show for an unsigned bundle; reverted on the owner's suggestion).

## Verified

- Gate `scripts/check.py --model` 10 PASS on main; Pages deploy green on `8a091ae`.
- Linux X11 39/39 (with a Qt app), GNOME 12/12. Windows (patched PIME, VM) Notepad 15/15, Edge 14/14 + 1 known
  (Ctrl shortcuts, G01, tabled). Mac VM 9/9 after the owner added cd_AI by hand and relogged.
- Live Claude Code (haiku, owner's quota): per-conversation agent, textbox MCP, Allow/Deny, Esc.

## Pending / waiting on the owner

- Mac VM: the lowercase cd icon and the "cd_AI" display name (64fbfaa) are merged but not yet
  built on the VM. A rebuild needs the owner's Allow click and a relogin (a bundle overwrite is
  not picked up until login), so do it when they are around. The VM checkout is on an older
  branch (`macname`, a02625b): `git fetch && git checkout main` first.
- macOS: the first suggestion after a reinstall was missed three times; it never reproduced by
  restarting the process (8/8). Likely the first-launch check of a new ad-hoc-signed app; the rig
  now waits 20 s. `launchctl setenv CLAUDISH_TRACE` did not reach an IME relaunched with
  `open -g` — tracing needs another route if it recurs.
- Parked: Claude API tool loop (needs a key); G30 auto-update (needs releases); G21 trained
  model; visual pass (macOS custom candidate panel, PIME candidate window, demo/home polish);
  upstream PIME proposal (a public post: needs the owner's OK). Linux GTK reports no selection (Qt does: rewriting a selection is verified there).

## Environment and owned resources

- Mac VM: `ssh -i ~/.ssh/claudish_mac_vm claudish@10.0.0.251`, passwordless sudo, repo ~/claudish,
  service `nohup python3 -m claudish serve --backend rules`, rig tests/desktop/macos/driver.py.
  Never write AppleEnabledInputSources (consent is the owner's).
- Windows VM `claudish-windows` (container, 8 GB, 6 cores; stop with
  `tests/desktop/windows/vm.sh stop`): Claudish's patched PIME (platforms/windows/pime, built
  there with VS 2022 Build Tools: jobs/buildtools.ps1, build-pime.ps1). Loop: `vm.sh sync`,
  `vm.sh run jobs/deploy.ps1 40`, `vm.sh run jobs/typing-core.ps1 90`; `vmscreen.sh OUT.png`.
- Models in `models/` (untracked): Qwen 0.5B/1.5B/14B, Qwen3-30B-A3B (framework checks with
  `llama-server --jinja -ngl 99`), Qwen2.5-VL-3B (F8). Extras venv `.tools/claude-venv`.
- claudish.io: site/ plus the static demo at /demo/ (wllama in the browser), deployed by
  .github/workflows/pages.yml on every push to main.
- Merge rule: clean `check.py --model` on the merged result (and a `ci/*` run for Windows/macOS
  packaging), check `git branch --show-current` before merging; main is fast-forward only.
