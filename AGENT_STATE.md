# Maintainer handoff

Checkpoint 2026-10-23 (latest), `main` at `aefd5c8`. An interactive session on the Spark; no 24/7 runner.

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

## Architecture (owner's direction: "an universal entrypoint to all AIs at caret")

- docs/design/architecture.md, done (G43): every request = the text box (claudish/turn.py `Box`:
  kind, app, text around the caret, observations, constraints) + what the user did (mode) + what is
  available (tools); one loop `Rewriter.answer` for /suggest and sessions; the model answers with
  complete / replace / insert / ask (`user__ask`); helpers are tools behind a question (G39); a
  turn whose task went to a helper ends as `done`. Bindings route an app to a profile (G38).
- Measured: fidelity 38/41 unchanged; terminal set Qwen3 30B 20/23, Qwen 1.5B 7/23 (was 2/23).
  Live on Qwen3 30B: handoff, "did you mean", clarification, and plain answers all as intended.
- Owner works hands-off on this: think at the architecture level, never per-situation patches.
- Since: agents' own questions (AskUserQuestion) are ask (live, haiku); `claudish recent` (memory
  only, 10 min, redacted, --clear); round-3 safeguards (model questions marked, whole task shown,
  who answered, secure fields refused by the service); a profile per mode; named helpers and a
  launcher; Claude backend in the same tool loop (stand-in SDK only, no key); `user__show` (an
  answer to read). Codex reads a Claudish note fine (via stdin: its bwrap sandbox cannot start on
  the Spark). Merges only after a clean gate summary (one slip on b40121f, fixed in 7e199dd).
- Mac VM: its installed cd_AI predates the service token; rebuild + relogin with the owner.

## Since the last checkpoint

- G35 (terminals): the service reads a focused terminal through AT-SPI / UI Automation (ctypes) / AX
  on Tab or Enter in compose; continue is quiet in terminals; never at a password prompt. Linux rig
  40/40 (GNOME Terminal), Windows VM 4/4 (Windows Terminal portable zip in the VM share's wt/, the
  classic console), Mac by hand (the rig's Terminal step fails only after its earlier scenarios: open).
  `claudish fix` and its hooks are retired; benchmarks/evaluate_terminal.py: Qwen3 30B 20/23.
- G36: per-run service token (~/.config/claudish/service-token, 0600) sent by the adapters.
  **The Mac VM's installed cd_AI predates it**: rebuild + relogin with the owner before running the
  rig against a current service (the VM's service is still an older checkout).
- Persona poll (docs/research/2026-10-23-persona-poll.md) produced G36–G41; owner decisions pending:
  Space picks draft 1, Enter's meaning in compose, a plain register by default, releases/signing.
- Next: G38 per-app routing.

## Verified

- Gate `scripts/check.py --model` 10 PASS on main; Pages deploy green on `8a091ae`.
- Linux X11 39/39 (with a Qt app), GNOME 12/12. Windows (patched PIME, VM) Notepad 15/15, Edge 14/14 + 1 known
  (Ctrl shortcuts, G01, tabled). Mac VM 8/8 on `8fc0332` (rebuilt, owner relogged; the lowercase cd icon shows in the menu bar; the first suggestion after the reinstall arrived).
- Live Claude Code (haiku, owner's quota): per-conversation agent, textbox MCP, Allow/Deny, Esc.

## Pending / waiting on the owner

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
