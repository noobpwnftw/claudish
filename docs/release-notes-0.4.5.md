# cd_AI 0.4.5

- Claude with an API key answers again: rewrites, instructions, versions and follow-ups, tools,
  questions and window pictures. The answer's format is one the Anthropic API accepts (0.3.0 to
  0.4.4 sent one it refused, and every request through an API key failed). An instruction's
  versions are three at most from every backend.
- macOS: the programs cd_AI starts (MCP servers, context commands, agents) no longer get its
  bundle's Python settings. An MCP server written in Python failed to start, and its tools never
  reached the model.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26 and 27, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.4.5/scripts/install.sh \| sh` |
