# cd_AI 0.1.1

- A conversation belongs to its text box on Linux, as on macOS and Windows.
- Shift+Esc brings back a held exchange as it was, without asking the model again.
- On Windows a shortcut while an instruction is out holds its exchange instead of typing it.
- Words typed while an instruction works stay: a question that comes shows them as Waiting and gives
  them back once answered; when the instruction ends elsewhere they are the next composition; Tab
  on an answer to read keeps them.
- An answer to read goes in with one Tab, and the model is not asked again; a reply typed over it
  reaches the model.
- Questions come one at a time. An answer reaches the service once; a lost reply is retried, and
  an answer that cannot be sent ends the instruction.
- "Is it done?" follows a Claude Code session started at a terminal prompt.
- Tab confirms every choice; the panel keeps its size while you choose; Enter and Shift+Enter on a
  highlighted row light its Tab.
- macOS: MCP tools and MCP context work in the app.
- Windows: each account has its own logon task.
- Panels keep their keys when a status is long, on every platform.
- Token budgets fit models that think first; the local Gemma starts with reasoning off.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.1.1/scripts/install.sh \| sh` |
