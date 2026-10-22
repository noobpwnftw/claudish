# Maintainer handoff

Checkpoint 2026-10-22 (an interactive session on the Spark; no 24/7 runner).

- `main` holds everything merged: the verified download (G02 slice),
  AltGr/Option typing (G07), the adapter smokes in CI (G08), the fidelity
  evaluation (G03), the prompt experiments (G11), and configurable backends and
  templates (G13). Each branch's CI passed before the merge. The merged result
  passed locally: 34 unit tests, compileall, the IBus and PIME smokes, a real
  Qwen 0.5B rewrite, and the browser acceptance suite.
- Owner direction: Claudish is a configurable entry point for AI at the caret
  (models, then MCP and context, then invocation modes). Model quality belongs to
  the model. The name and the em dashes stay. See the ROADMAP preamble.
- Evidence limits: native desktop typing is unverified (G01). The Claude backend
  is tested with the real SDK against a loopback stub, never against the live
  API, because there are no credentials on the Spark.
- Environment: `gh` is unauthenticated; read CI through the public API. Pushes
  work through VS Code Remote's askpass (see Claude memory, `vscode-git-push-auth`).
  For browser tests, pass `--executable ~/.cache/ms-playwright/chromium-1243/chrome-linux-arm64/chrome`.
  Local test assets: `.tools/pime/textService.py` (pinned) and
  `.tools/claude-venv` (anthropic 2.1.0).
- Next action: G14, one config file with profiles, the foundation for G10 (MCP
  context) and G15 (invocation modes). After that: the G09 next-word metric.
- Owned background work: none. Ports 18765/18766 are free. The untracked
  `models/qwen2.5-1.5b-instruct-q4_k_m.gguf` (1.1 GB, verified) is left from G11.
