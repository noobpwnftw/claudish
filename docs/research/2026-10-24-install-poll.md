# How to cross onboarding and visuals: a poll of developers and product managers, 2026-10-24 (synthetic)

Five reviewers, each an agent with a persona, read the repository and a brief
([the facts given](#the-facts-they-were-given)) and answered how to cross the next two
milestones, onboarding and visuals, without feature creep, with no Apple Developer ID and as
little friction as possible: an indie macOS developer who ships without a Developer ID, a Windows
desktop developer, a consumer product manager, a developer-tools product manager, and an
open-source release engineer.

## Where they agreed

- **One prebuilt bundle per OS with its own Python**: no git, venv or pip for anyone (all five).
- **The installer registers and enables the input method**, so there is no adding it by hand and
  no logout: `TISRegisterInputSource` and `TISEnableInputSource` as the console user on macOS
  (macOS still shows its own Allow for an unsigned input method), `InstallLayoutOrTip` on Windows.
- **A small settings window, not a wizard** (four of five; the release engineer preferred the
  existing `claudish setup` behind thin installer pages): "Settings…" in the input menu, opened
  once by the installer at the end, which is the whole first run. Version one: the key (or its
  status), the voice, "use a local model instead". The key goes where the service can read it
  and never into config.json: the Keychain on macOS, the user's profile on Windows (not from the
  elevated installer, which can land in the administrator's profile), a 0600 file on Linux.
- **Cut for now:** auto-update, signing, Homebrew (casks that fail Gatekeeper are leaving the
  official tap), .dmg, MSIX (TSF DLLs are unsupported there), Linux packages, a GUI uninstaller,
  template editing in the window, hot reload, fcitx5, the share card. Continue, F8 and agents stay
  out of first-run copy.
- **Visuals, done for a user:** the panel never clips or covers the caret and reads as native in
  light and dark at 1x and 2x, with one check at 150% and one in high contrast; the settings window
  looks like a system pane. Stop pixel-matching the lab beyond that (the developer-tools PM would
  still finish the full G45 sign-off).

## macOS without a Developer ID

Measured on macOS 26.6 (the project's VM) with an ad-hoc signed bundle: a quarantined .pkg shows
"Not Opened" (Move to Trash, Done); System Settings > Privacy & Security then shows "was blocked
to protect your Mac" with Open Anyway; a second dialog offers Open Anyway again; then the
password. "Allow applications from" offers only the App Store options. A file fetched with curl
has no quarantine and opens without any of this.

The reviewers split on which to put first, both installing the same .pkg:
- the download button, with a three-frame picture of the Open Anyway path beside it (the Mac
  developer: people follow a picture, not text; expect about 30% of non-developers to stop there);
- a one-line `curl ... | sh` (or `curl -O` then `sudo installer`) in Terminal, which meets no
  Gatekeeper prompt (the developer-tools PM, the consumer PM, the release engineer).

## Windows without a certificate

One per-machine Inno Setup installer: Claudish's patched PIME, an embeddable Python with the
dependencies in it, the VC++ runtime for ARM; it registers the text service and runs the service
under PIME's launcher (the separate logon task goes). A browser download meets SmartScreen ("More
info", "Run anyway") and UAC; `winget install` downloads without the mark of the web, so only UAC
(winget-pkgs accepts unsigned installers). An OV certificate no longer clears SmartScreen on day
one; Azure Trusted Signing (about $10 a month) would, where the owner's entity qualifies.

## The risks they named

- **The key wall** (both product managers): a writer with no Anthropic account meets a sign-up, a
  card and billing before any value; the fallbacks are the browser demo and the 4.9 GB local
  model. A hosted trial would be creep (cost, abuse, a privacy story).
- **An input method that freezes typing** (the Mac developer): every service call asynchronous
  with a short timeout, falling back to plain typing; a test with the service stopped and the
  network off.
- **Defender** (the Windows developer): an unsigned DLL in every process that reads text and
  talks to the network looks like a keylogger; submit each build as a false positive in advance
  and test on a clean Windows 11.
- **A bundle that works in CI but not at login** (the release engineer): the input method and the
  service on a different interpreter or path; gate every release on a clean VM per platform:
  install, log in, Tab lands a rewrite.

## The facts they were given

Today's install (git, a venv, pip, a key, `claudish setup`, logging out, adding the source by
hand); the macOS measurements above; Windows' patched PIME needing an administrator install;
Linux IBus needing a logout; the visual state (the natives match the design lab; sign-off at
150/200%, high contrast and text scaling open; no settings UI yet); and the owner's constraints:
avoid feature creep, straightforward (a wizard or a settings panel under the input method), no
Developer ID, as frictionless as possible.

## The owner's answers

- macOS: the site's Download button first (the .pkg, with a three-frame picture of the Open
  Anyway path), the Terminal one-liner second.
- First run: one settings window (opened from the input menu, and once at the end of install),
  not a wizard. Roadmap: G61 (installers), G62 (the window), G63 (release gates), and G45 with
  the reviewers' user-level acceptance.

