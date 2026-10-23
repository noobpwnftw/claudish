# Install

How to set up Claudish step by step, run the model and service, and register the input method on each OS. The short version is in the [README](../README.md#install).

## Quick start

**One command:** with Python 3.10+, from this checkout:

```sh
python -m claudish setup
```

It shows each step and asks before doing it: write a config, import MCP servers
from your Claude setup, download a pinned llama.cpp build and the model (both
SHA-256 verified), register the input method, start Claudish at login, then run
`doctor`. Steps already done are skipped, so it is safe to run again.
`--dry-run` shows the plan, `--yes` does it all, and `--profile claude` sets up a
hosted profile instead (no model download). Installing the input method on
Windows and macOS needs an administrator, so setup prints that command. Verified
end to end on Ubuntu 24.04 under systemd in a container (`tests/desktop/linux-systemd`).

Or step by step:

1. **Try it in your browser.** With Python 3.10+:

   ```sh
   python scripts/download_llama.py
   python scripts/download_model.py small
   python scripts/start.py
   ```

   Open http://127.0.0.1:18765, then switch between Rewrite, Continue, and
   Instruct. Each mode has its own sample phrases. No model handy? `python -m
   claudish serve --backend rules` runs the demo with simple stand-ins.
2. **Pick a brain.** `python -m claudish init` writes `~/.config/claudish/config.json`
   with four profiles: `local` (the default), `ollama` (any OpenAI-compatible
   server), `claude` (your API key), and `agent` (an agent CLI such as
   `claude -p`). Choose one with `python -m claudish serve --profile NAME`.
3. **Install the input method** for [Linux](#linux-input-method),
   [Windows](#windows-input-method), or [macOS](#macos-input-method), and add
   **cd_AI — Claudish** in your input sources.
4. **Start it at login.** `python -m claudish service install` runs the local
   stack (model and service) at every login: a systemd user unit on Linux, a logon
   task on Windows (no console window), a launch agent on macOS. Use
   `service install --serve -- --profile claude` for another profile, `service
   status` and `service uninstall` to inspect or remove it, and `--dry-run` to see
   what it would do.
5. **Check the setup.** `python -m claudish doctor` walks the whole chain (model,
   service, config, the input method's registration on your OS, and context
   sources) and prints a fix for anything wrong. On Linux, for example, it
   catches a session that started before the installer's search-path change
   ("log out and back in"); on Windows on ARM, PIME's missing x86 runtime.
6. **Learn five keys.** Everything else is typing.

| Key | Does |
| --- | --- |
| Shift (tap) | switch: continue ↔ compose |
| Tab | take the model's text: the rest of the sentence, a rewrite (shown first; Tab again puts it in), the highlighted draft (with nothing offered, Tab is the app's) |
| Enter | compose: send your words as an instruction (they stay underlined while the model works), a reply, or the answer to a question; it never inserts the model's text; with nothing composed, the app's |
| Shift+Enter | compose: keep your words as typed |
| ↑ ↓ | choose a draft (Tab inserts it) or an answer (Enter sends it); choices are not numbered: digits are text |
| Esc | one step back: what you typed → edit (your instruction back at the caret) → dropped; Shift+Esc brings it back |
| F8 | in compose, with an instruction: also send a picture of the window you are typing in |

## Start the model and service

Python 3.10+ runs the service. It has no pip runtime dependencies. Run commands
from this project directory.

Both download scripts use only the standard library and verify before installing;
an interrupted download leaves nothing behind, and a verified file is not
downloaded again. `download_llama.py` fetches a pinned
[llama.cpp](https://github.com/ggml-org/llama.cpp/releases) release build
(`b11822`, 12–24 MB) for your OS and CPU into `.tools/`, checked against the
SHA-256 GitHub publishes for it: the CPU build runs everywhere and uses Metal on
Apple silicon; `--variant vulkan` uses most GPUs on Linux and Windows.
`download_model.py` fetches the pinned upstream revision of the model into
`models/`, checked against the tested file's size and SHA-256. Set `HF_ENDPOINT`
to use a mirror.

```sh
python scripts/download_llama.py
python scripts/download_model.py small
python scripts/start.py
```

`start.py` uses `llama-server` from your `PATH` first, then the downloaded build;
pass `--server /path/to/llama-server` (`llama-server.exe` on Windows) to use
your own build, for example one with CUDA. On the Spark's CPU, the downloaded
CPU build takes a median 82 ms per short rewrite (4 threads, warm). The service listens on `127.0.0.1:18765`; the model listens
on `127.0.0.1:18766`. Ctrl+C stops both processes. Nothing is installed at startup.

This checkout already contains both GGUF models and a CUDA-enabled llama.cpp
build under the ignored `models/` and `.tools/` directories. On this Spark:

```sh
python3 scripts/start.py
```

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

On a Mac with a framework build of Python 3.10+ (for example, from python.org):

```sh
python3 platforms/macos/build.py --install
```

This creates an isolated build environment, installs macOS build dependencies,
builds `dist/macos/Claudish.app`, applies a local ad-hoc signature, and copies it
to `~/Library/Input Methods/Claudish.app`. It does not change your active input
source. Omit `--install` to build only. These commands must run on macOS; the
Spark cannot build or validate a native Mac app bundle.

Then log out and back in, and add it in **System Settings → Keyboard → Input
Sources → Edit… → + → English → cd_AI**. macOS asks you to allow a third-party
input method there; nothing can add it for you. After you update cd_AI, log out
and back in again: until then macOS keeps using the bundle it loaded (its name,
its icon, and sometimes the old code).

Log out/in, then add Claudish under **System Settings → Keyboard → Text Input →
Edit → +** (look under English). Choose it using the Input menu or your configured
input-source shortcut. Start the service separately:

```sh
python3 scripts/download_model.py small
python3 scripts/start.py --server /path/to/llama-server
```

Use a macOS llama.cpp build; Apple Silicon builds can use Metal. Mac inference
performance has not been measured. Alternatively, forward the Spark's service
to the Mac's `127.0.0.1:18765` over SSH and leave inference running on the Spark.

The candidate panel refreshes automatically, and the keys are the same as on the
other platforms (above). Navigation keys and Command or
Control shortcuts commit the current wording before being passed through.
Characters typed with Option, such as — and €, stay in the composition.
Composition edits currently work at the end of the buffer. Secure fields and
application-specific composition behavior need native acceptance testing.

This is a development bundle, not a notarized release installer. Distribution
to other users needs Developer ID signing and notarization. To uninstall or
replace it, switch to another input source, remove Claudish from Input Sources,
remove `~/Library/Input Methods/Claudish.app`, and log out/in. The installer
refuses to overwrite an existing installed app.
