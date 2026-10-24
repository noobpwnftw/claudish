# Install

How to set up Claudish, give it a model, and register the input method on each OS. The short
version is in the [README](../README.md#install).

## Quick start

You need Python 3.10+, git, and a model to point it at. cd_AI ships no model: out of the box it
is set up for Claude with your own API key, which works on any computer. With a GPU or Apple
silicon, the local model below made slop as well as anything we tried.

1. **Get it**, with the Claude SDK, in a virtual environment of its own (current Ubuntu, Debian
   and Homebrew Pythons refuse a plain `pip install`):

   ```sh
   git clone https://github.com/noobpwnftw/claudish
   cd claudish
   python3 -m venv .venv
   .venv/bin/python -m pip install -e ".[claude]"
   ```

   On Windows the venv's Python is `.venv\Scripts\python`. Run every `claudish` command below
   with it; the login service setup installs runs on it too.

2. **Run setup:**

   ```sh
   .venv/bin/python -m claudish setup
   ```

   It asks which voice you want (corporate slop unless you pick another: `proofread` keeps your
   words for work), then shows each step and asks before doing it: write a config (profile
   `claude`), import MCP servers from your Claude setup, check the model, register the input
   method, start Claudish at login, then run `doctor`. Steps already done are skipped, so it is
   safe to run again. `--dry-run` shows the plan and `--yes` does it all. Installing the input
   method on Windows and macOS needs an administrator, so setup prints that command.

3. **Give it your key** in cd_AI's settings:

   ```sh
   .venv/bin/python -m claudish settings
   ```

   It opens the settings in your browser (on macOS, **Settings…** in the input menu opens them
   in a window). Paste your Anthropic API key and Save: cd_AI checks it with Anthropic, saves it
   where the service reads it (the Keychain on macOS, a file only you can read beside the config
   elsewhere), and uses it from your next keystroke. It never goes into the config. The same
   page picks the voice, or a model server on this computer instead of Claude.

   Keys from elsewhere work too: `ant auth login` (the Anthropic CLI), or `ANTHROPIC_API_KEY` in
   your account's environment (a variable you `export` in a terminal does not reach a service
   started at login).

4. **Log out and back in**, add **cd_AI — Claudish** in your input sources, and type: Tab asks
   for the rewrite, Enter sends an instruction. The keys are in the [README](../README.md#keys).

Verified end to end on Ubuntu 24.04 under systemd in a container (`tests/desktop/linux-systemd`).

**Another model:** `python3 -m claudish init` writes `~/.config/claudish/config.json` with
profiles to start from: `claude` (the default), `ollama` (any OpenAI-compatible server, local or
hosted), `local` (below), and `agent` (an agent CLI such as `claude -p`). Run setup with
`--profile NAME`, or see [configuration](configuration.md). With no model at all, compose says
"no model is set up" and nothing you type is lost.

**Continue** (a Shift tap) types straight into the app. It suggests the rest of a sentence only
with a local model, or with a model a profile routes to it ([configuration](configuration.md#modes)),
because it asks at every pause.

**Start at login by hand:** `python3 -m claudish service install` runs `claudish serve` with
the config's profile at every login: a systemd user unit on Linux, a logon task on Windows (no
console window), a launch agent on macOS. Pass `-- --profile NAME` for another profile, `--local`
for the local model below; `service status` and `service uninstall` inspect or remove it, and
`--dry-run` shows what it would do. `python3 -m claudish doctor` walks the whole chain (model,
service, config, the input method's registration, context sources) and prints a fix for anything
wrong.

**Try it without installing the input method:** `python3 -m claudish serve` and open
http://127.0.0.1:18765, or `--backend rules` for simple stand-ins with no model.

## A local model (optional)

For a model on your own machine: free per keystroke, private, and what lets continue suggest at
every pause. The one setup installs is Gemma 4 E4B (Apache-2.0, 4.9 GB), which made slop as well
as anything we tried, a frontier model included ([benchmarks](../benchmarks/README.md#choosing-the-models-g53-2026-10-24)).
It answers in about 0.6 s on a GPU or Apple silicon and 3–4 s on a CPU alone; models small enough
to be fast on any CPU make no usable slop.

```sh
python3 -m claudish setup --profile local
```

Setup downloads a pinned [llama.cpp](https://github.com/ggml-org/llama.cpp/releases) release
build (`b11822`, 12–24 MB, the CPU build; Metal on Apple silicon; `--variant vulkan` for most GPUs
on Linux and Windows) into `.tools/` and Gemma 4 E4B (QAT Q4_0) into `models/`, both checked
against their published SHA-256, and runs them at login. The same by hand:

```sh
python3 scripts/download_llama.py
python3 scripts/download_model.py gemma
python3 scripts/start.py
```

Both download scripts use only the standard library; an interrupted download leaves nothing
behind, and a verified file is not downloaded again. Set `HF_ENDPOINT` to use a mirror.
`start.py` uses `llama-server` from your `PATH` first, then the downloaded build; pass
`--server /path/to/llama-server` (`llama-server.exe` on Windows) to use your own, for example
with CUDA. The service listens on `127.0.0.1:18765`, the model on `127.0.0.1:18766`; Ctrl+C stops
both. Any other model works through llama.cpp or an OpenAI-compatible server
([configuration](configuration.md)).

## Linux input method

Requires an IBus desktop and system Python with PyGObject and IBus bindings.
On Ubuntu/Debian:

```sh
sudo apt install ibus python3-gi gir1.2-ibus-1.0
/usr/bin/python3 platforms/linux/install.py            # per user, no sudo
# or, for sessions that do not read ~/.config/environment.d:
sudo /usr/bin/python3 platforms/linux/install.py --system
```

IBus only reads engine definitions from `IBUS_COMPONENT_PATH`, which defaults to
`/usr/share/ibus/component`. The per-user install therefore writes
`~/.config/environment.d/90-claudish-ibus.conf` to add `~/.local/share/ibus/component`.
systemd-managed sessions, including GNOME, apply it at the next login. The
installer does not change the active keyboard. Log out and back in, then add
**English → cd_AI — Claudish** to Input Sources and select it with your input-source
shortcut while the service is running. The engine keeps your keyboard layout, so
AltGr and dead keys still work. The project directory must stay at its
installed path. Remove with `install.py --uninstall` (add `--system` if you
installed that way), then log out and back in.

Wayland/X11 application coverage depends on the desktop's IBus integration.
This adapter does not support an Fcitx-only session or a raw terminal console.

## Windows input method

Install [PIME](https://github.com/EasyIME/PIME) **with its Python backend** first.
PIME supplies the native Windows Text Services Framework component. Claudish
provides a Python service loaded by that component, rather than a keyboard hook.

In an administrator PowerShell:

```powershell
.\platforms\windows\install.ps1
# For a different PIME location:
.\platforms\windows\install.ps1 -PimeRoot 'C:\Program Files (x86)\PIME'
```

cd_AI needs Claudish's own PIME ([platforms/windows/pime](../platforms/windows/pime/README.md)):
it shows answers as they arrive, tells cd_AI the text around the caret, and draws cd_AI's
candidate window. A released PIME is not supported. Until Claudish ships its build, it is built
from source with the Visual Studio C++ tools.

This copies the plugin and shared modules into PIME's input-method directory
and re-registers its existing x86/x64 DLLs so it can enumerate the new profile.
Sign out/in and select **cd_AI — Claudish** using Win+Space. Run the model and
service in a normal user terminal. The plugin uses PIME's embedded Python;
the model/service use your separate Python 3.10+ installation.

**Windows on ARM:** use a PIME build with ARM64X support (newer than
2.0.0-beta3; the [AppVeyor master builds](https://ci.appveyor.com/project/EasyIME/pime)
have it), and install the
[x86 VC++ runtime](https://aka.ms/vs/17/release/vc_redist.x86.exe). PIME's launcher is
an x86 program; without that runtime it finds an ARM64 `vcruntime140.dll` on your
`PATH` (Python for ARM64 puts one there) and fails with error `0xc000007b`, so every
PIME input method types plain text. Verified on Windows 11 ARM64 (build 26100) in
classic Notepad: 9 typing scenarios, `tests/desktop/windows`.

To remove Claudish, remove its input profile in Windows settings, then remove
`PIME\python\input_methods\claudish`. Keep PIME itself if you use other PIME input
methods.

## macOS input method

The adapter uses Apple's [InputMethodKit](https://developer.apple.com/documentation/inputmethodkit/imkinputcontroller)
through [PyObjC](https://pyobjc.readthedocs.io/en/latest/apinotes/InputMethodKit.html).
The builder uses py2app to bundle Python, the adapter, and its shared modules
into `Claudish.app`. The model runs in a separate process as on Windows/Linux.

**The installer.** Until there is a release to download, build it on a Mac with Python 3.10+
from python.org:

```sh
python3 platforms/macos/build.py
python3 platforms/macos/package.py
open dist/macos/cd_AI.pkg
```

`cd_AI.pkg` installs for you alone (`~/Library/Input Methods`, no administrator password) and does
the rest: a starter config, the service at every login, and cd_AI added to your input sources and
selected. macOS asks once to allow it to enable cd_AI. On a first install, cd_AI's settings open at
the end: paste your Claude key, pick a voice. Then **log out and back in**, as after installing or
updating any macOS input method: until then macOS keeps its old list of input sources (and, after
an update, the old cd_AI). **Settings…** in the input menu opens the settings again.

The package is ad-hoc signed, not notarized. A copy downloaded with a browser is blocked the first
time ("Not Opened"); **System Settings → Privacy & Security → Open Anyway** lets it through.
`installer -pkg cd_AI.pkg -target CurrentUserHomeDirectory` in Terminal installs it without that.

The bundle is cd_AI's whole command line too: `~/Library/Input Methods/Claudish.app/Contents/MacOS/Claudish`
takes `doctor`, `settings`, `service status` and the rest. For development, `build.py --install`
copies only the bundle; then add it by hand in **System Settings → Keyboard → Text Input → Edit →
+** (under English), and log out and in after each update.

The candidate panel refreshes automatically, and the keys are the same as on the
other platforms (above). Navigation keys and Command or
Control shortcuts commit the current wording before being passed through.
Characters typed with Option, such as — and €, stay in the composition.
Password fields get their keys untouched.

**Uninstall:** `Claudish service uninstall` (the bundle's command line, above), switch to another
input source and remove cd_AI from your input sources, then delete
`~/Library/Input Methods/Claudish.app`. Your config stays in `~/.config/claudish/`, and a saved key
in the Keychain under "cd_AI".
