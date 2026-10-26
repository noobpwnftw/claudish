# Install

How to install cd_AI on each OS, give it a model, and remove it. The short version is in the
[README](../README.md#install).

cd_AI ships no model. Out of the box it is set up for Claude: its settings, which open at the end
of every install, take an [Anthropic API key](https://console.anthropic.com/settings/keys), or
**Claude Code** for a Claude subscription (it runs Claude Code's `claude` command, logged in to that
subscription, kept running beside the service), or **Codex** for a ChatGPT subscription (it runs Codex's
`codex` command the same way), or the address of another model API.

Pick a model, then use **Try a rewrite** in Settings before switching input
methods. Subscription choices show when their command is starting or needs a login. After
logging in through that command, try the rewrite again. Once it answers, finish the OS steps below:
type `ok`, press Tab to preview the rewrite, then Tab again to insert it. Enter keeps `ok` (the next Enter is the app's).

## The `claudish` command

Every install includes cd_AI's command line, `claudish`: `claudish settings`, `claudish doctor`,
`claudish service status` and the rest.

- **Linux:** the one-line installer links it into `~/.local/bin`, which is on PATH on most desktops
  (a new login adds it).
- **Windows:** the installer adds it to PATH; open a new terminal after installing.
- **macOS:** it is inside the app bundle:
  `~/Library/Input\ Methods/Claudish.app/Contents/MacOS/Claudish`. To type `claudish`, add
  `alias claudish=~/Library/Input\ Methods/Claudish.app/Contents/MacOS/Claudish` to `~/.zshrc`.
- **A source checkout:** its virtual environment has it, at `.venv/bin/claudish`
  (`.venv\Scripts\claudish` on Windows).

## Linux input method

IBus only (fcitx5 is not supported yet). One line, as your user:

```sh
curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.2.0/scripts/install.sh | sh
```

It checks for git, Python 3 and the IBus bindings (and names the `apt install` line for any that
are missing), clones cd_AI into `~/.local/share/claudish`, makes its own Python environment there,
links `claudish` into `~/.local/bin`, and runs `claudish setup`. Setup asks for a tone, writes the
config, registers the input method with IBus, starts the service at every login (a systemd user
unit), and opens cd_AI's settings in your browser. Then **log out and back in**, and add
**English → Claudish** in **Settings → Keyboard → Input Sources**. Running the same line
again updates cd_AI and restarts its service.

**By hand**, from a checkout: `sudo apt install ibus python3-gi gir1.2-ibus-1.0`, then

```sh
/usr/bin/python3 platforms/linux/install.py            # per user, no sudo
sudo /usr/bin/python3 platforms/linux/install.py --system   # for sessions that do not read environment.d
```

IBus reads engine definitions from `IBUS_COMPONENT_PATH` (default `/usr/share/ibus/component`), so
the per-user install writes `~/.config/environment.d/90-claudish-ibus.conf` to add
`~/.local/share/ibus/component`; systemd-managed sessions, including GNOME, apply it at the next
login. The engine keeps your keyboard layout. The checkout must stay where it is.

**Uninstall:**

1. Remove **English → Claudish** from **Settings → Keyboard → Input Sources**.
2. `claudish service uninstall`
3. `/usr/bin/python3 ~/.local/share/claudish/platforms/linux/install.py --uninstall`
4. `rm -rf ~/.local/share/claudish ~/.local/bin/claudish`
5. Log out and back in.

The config stays in `~/.config/claudish/`.

## Windows input method

**The installer**, `cd_AI-setup.exe` from the [latest release](https://github.com/noobpwnftw/claudish/releases/latest), for x64 and ARM64 Windows 11. It installs cd_AI's text service (its own build of PIME), a Python of its own for the service, and the `claudish` command, and adds
cd_AI to your input sources. It asks for an administrator once, then sets up a starter config and
the service at every login, and opens cd_AI's settings in your browser (the key, the tone). Then
**restart**, and pick **Claudish** with Win+Space: it is listed under **English (United States)**, shown as
ENG in the taskbar. An update also asks for a restart: the text service is
loaded in every app, so Windows replaces it at the next one.

cd_AI is an **English (United States)** input source (ENG in the taskbar) and types with the US
keyboard layout, as English (United States) does. On a Japanese (JIS) keyboard its symbols follow
the US positions: Shift+2 types @, and Shift+7 types &.

It is not signed: SmartScreen shows "Windows protected your PC"; **More info → Run anyway** lets it
through.

**Uninstall:** **Settings → Apps → Installed apps → cd_AI → Uninstall**. It takes cd_AI out of your
input sources; the text service's files, loaded in running apps, go at the next restart. The config
stays in `%USERPROFILE%\.config\claudish`.

**Building the installer** (development). cd_AI's PIME
([platforms/windows/pime](../platforms/windows/pime/README.md)) is PIME with Claudish's patches: it
shows answers as they arrive, tells cd_AI the text around the caret, draws cd_AI's panel, and has
names of its own (its CLSID, its home beside its DLL, its launcher's pipe). On Linux,
`platforms/windows/pime/make_source.sh pime-src.zip` prepares the patched source. On Windows with
the Visual Studio 2022 C++ tools (`buildtools.ps1` installs them), `build-pime.ps1` builds the text
service for x86, x64 and ARM64 and the launcher (Rust, installed on first use) into a tree of a
released PIME's files; then, with Python 3.10+ and Inno Setup 6, `python platforms\windows\package.py`
writes `dist\windows\cd_AI-setup.exe`.

## macOS input method

**The installer**, `cd_AI.pkg` from the [latest release](https://github.com/noobpwnftw/claudish/releases/latest), for Apple silicon (Intel Macs are not supported yet). It installs
for you alone (`~/Library/Input Methods`, no administrator password): the app, a starter config,
the service at every login, and cd_AI added to your input sources and enabled. macOS asks once to
allow it to enable cd_AI. On a first install, cd_AI's settings open at the end: choose your model
and tone, then use Try a rewrite. Then **log out and back in**, as after installing or updating
any macOS input method: until then macOS keeps its old list of input sources (and, after an update, the old cd_AI).
In the input menu it is **Claudish — Compose** and **Claudish — Continue**: a Shift tap switches
between them, the menu bar showing AI or cd. **Settings…** in the input menu opens the settings again.

For a model API on another computer, macOS asks for local-network access on the first connection.
Choose **Allow**, then retry **Use this API** in Settings if its first check did not connect.

The package is ad-hoc signed, not notarized. A copy downloaded with a browser is blocked the first
time: click **Done**, then **System Settings → Privacy & Security → Open Anyway**, and **Open
Anyway** again in the dialog.
`installer -pkg cd_AI.pkg -target CurrentUserHomeDirectory` in Terminal installs it without that.

**Building the package**, on a Mac with Python 3.10+ from python.org:

```sh
git clone https://github.com/noobpwnftw/claudish && cd claudish
python3 platforms/macos/build.py
python3 platforms/macos/package.py
open dist/macos/cd_AI.pkg
```

For development, `build.py --install` copies only the bundle; then add it by hand in **System
Settings → Keyboard → Text Input → Edit → +** (under English), and log out and in after each update.

The keys are the same as on the other platforms ([Typing](using.md#typing)). ← and → move within
the composition; other navigation keys, Option+← and Command or Control shortcuts commit the current
wording and go to the app. Characters typed with
Option, such as — and €, stay in the composition.

**Uninstall:**

1. In **System Settings → Keyboard → Text Input → Edit**, select Claudish — Compose and Claudish —
   Continue and click **−**.
2. Paste into Terminal, which stops cd_AI's service and removes the app:
   `~/Library/Input\ Methods/Claudish.app/Contents/MacOS/Claudish service uninstall && rm -rf ~/Library/Input\ Methods/Claudish.app`
3. Log out and back in.

The config stays in `~/.config/claudish/`, and a saved key in the Keychain under "cd_AI" (Keychain
Access removes it).

## The model

**Claude** is the default: paste an API key in cd_AI's settings (`claudish settings`, or
**Settings…** in the input menu). cd_AI checks it with Anthropic, saves it, and uses it right away.
`ant auth login` (the Anthropic CLI) or `ANTHROPIC_API_KEY` in your account's environment work too;
a variable you `export` in a terminal does not reach a service started at login.

**Another model API:** the same settings page takes any OpenAI-compatible address (OpenAI,
OpenRouter, Groq, Ollama, LM Studio, llama.cpp) and a key if it needs one. `claudish init` writes
`~/.config/claudish/config.json` with profiles to start from: `claude` (the default), `ollama` (any
OpenAI-compatible server), `local` (below), `claude-code` and `codex` (the subscriptions), and
`agent` (an agent CLI such as `claude -p`); see
[configuration](configuration.md). With no model at all, compose says "no model is set up".

**A local model:** `claudish setup --profile local` downloads a pinned
[llama.cpp](https://github.com/ggml-org/llama.cpp/releases) build (`b11822`; the CPU build, Metal on
Apple silicon, `--variant vulkan` for most GPUs on Linux and Windows) and Gemma 4 E4B (Apache-2.0,
QAT Q4_0, 4.9 GB; [why this model](../benchmarks/README.md#choosing-the-models-g53-2026-10-24)),
and runs both at login. Continue (a Shift tap) suggests the rest of a sentence only with a local
model, or with a model a profile routes to it ([configuration](configuration.md#modes)); on
Claude, Claude Code and Codex it is plain typing.

## The service

`claudish service install` runs `claudish serve` with the config's profile at every login: a
systemd user unit on Linux, a logon task on Windows, a launch agent on macOS. Run again, it
restarts the service with the current settings; `--local` is for the local model;
`claudish service status` and `claudish service uninstall` inspect or remove it, and `--dry-run`
shows what it would do. `claudish doctor` walks the whole chain (model, service, config, the input
method's registration, context sources) and prints a fix for anything wrong.

Without the input method, `claudish serve` and http://127.0.0.1:18765 give the browser demo on your
model, or `claudish serve --backend rules` simple stand-ins with no model.

## From a source checkout

For development, or to run cd_AI from a checkout (Python 3.10+ and git):

```sh
git clone https://github.com/noobpwnftw/claudish && cd claudish
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[claude]"     # add mcp for MCP servers: ".[claude,mcp]"
.venv/bin/claudish setup
```

On Windows the venv's commands are under `.venv\Scripts\`. The checkout gives the service and the
command line; the Windows input method itself comes only from `cd_AI-setup.exe`, and the macOS one
from `cd_AI.pkg` (or `build.py --install`). For the local model by hand:

```sh
python3 scripts/download_llama.py
python3 scripts/download_model.py gemma
python3 scripts/start.py
```

`start.py` uses `llama-server` from your `PATH` first, then the downloaded build; `--server
/path/to/llama-server` picks another (for example a CUDA build). The service listens on
`127.0.0.1:18765`, the model on `127.0.0.1:18766`; Ctrl+C stops both. `HF_ENDPOINT` sets a mirror
for the model download.
