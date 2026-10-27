# cd_AI 0.3.1

- Windows: cd_AI's PIME is rebased on PIME 2.0.0-beta4. Its launcher drops requests left from
  before a backend restart and passes a closing text box on to the backend; the input method runs
  on PIME's Python 3.15.
- Windows: an update removes the files the previous version had and this one does not; the
  installer no longer carries leftover copies of replaced DLLs.
- The browser demo: a paste goes in as is, as in any app; Tab on a one-line selection composes it.

## Download

**Not signed.** macOS blocks the package once: click **Done** (not Move to Trash), then **System
Settings → Privacy & Security → Open Anyway**, twice. Windows SmartScreen says "Windows protected your
PC": **More info → Run anyway**. With Windows' **Smart App Control** fully on (not in evaluation), an
unsigned installer is blocked with no Run anyway.

| | File |
| --- | --- |
| macOS 26, Apple silicon (not Intel yet) | `cd_AI.pkg` |
| Windows 11, x64 and ARM64 | `cd_AI-setup.exe` |
| Linux, IBus | `curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.3.1/scripts/install.sh \| sh` |
