# Maintainer handoff

Checkpoint 2026-10-22 (an interactive session on the Spark; no 24/7 runner).

- `main` (`1fe465e`) adds since the last checkpoint: G10 context providers
  (file, command, MCP, caret text), extras tests in the gate, and G16 `claudish
  fix`. The gate `python scripts/check.py --model` passes. `agent/g16-bash3`
  (bash 3.2 support for macOS) is waiting on its `ci/g16-bash3` run before merge.
- Owner direction: Claudish is a configurable entry point for AI at the caret
  (models, then MCP and context, then invocation modes). Model quality belongs to
  the model. The name and the em dashes stay. See the ROADMAP preamble.
- Evidence limits: native desktop typing is unverified (G01). The Claude backend
  is tested with the real SDK against a loopback stub, never against the live
  API, because there are no credentials on the Spark.
- Environment: `gh` is authorized (account noobpwnftw) and set up for git. CI is
  opt-in via `ci/*` branches; check it with `gh run watch`. Local extras venv:
  `.tools/claude-venv` (anthropic 2.1.0, mcp 2.3.0). zsh is not installed, so
  the zsh hook is unrun.
- Next action: G15 invocation modes (rewrite, continue, instruct, fix) chosen
  per profile and switched by key, starting with the service API and the browser
  demo, then the adapters. G12 (a local judge model) in parallel.
- Owned background work: none. Ports 18765/18766 are free. The untracked
  `models/qwen2.5-1.5b-instruct-q4_k_m.gguf` (1.1 GB, verified) is left from G11.
