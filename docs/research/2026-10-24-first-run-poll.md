# First-run poll: the settings window and the macOS package (2026-10-24)

Five reviewers walked the first run as built on 2026-10-24 (the macOS package, the settings window,
README, docs/install.md, the site's install section): a non-technical Mac writer with no Anthropic
account, a consumer product manager, an indie Mac developer without a Developer ID, a Linux and
Windows developer, and a daily Rime/Pinyin user (whose view leads on input-method conventions).
Owner direction for the round: get the thing to work before anything else; no feature creep.

## Where they agreed

- **The biggest leak is that there is no download.** Building the package with python3 stops a
  writer before Gatekeeper ever shows; the README did not even say how to get the code on a Mac.
  A downloadable package is the owner's release decision.
- **The key wall:** a Claude key means an Anthropic account and prepaid credit, separate from a
  Claude subscription, and nothing said so. The window now says it and links the console.
- **Show the first rewrite before the logout:** after a key or a voice is saved, the window asks
  for one real rewrite ("ok" becomes ...), so the person sees what Tab will do.
- **No jargon where a person looks:** a literal "CFBundleName" in the input menu (fixed: the
  bundle is named cd_AI), "rules backend", config paths, a red status on a normal first run.
- **Log out and back in, said where it happens:** the package's last page, the window's first-run
  line, the docs, as Squirrel does.

## Changes made

The window's model server switches only after the server answers and has the model, offers the
server's own models, and says when the server is gone rather than "Ready" (a VM had been switched
to a server that was not there, and every rewrite failed). The starter's model name for it is gone.
The package is not relocatable, refuses to run as root, logs to ~/Library/Logs, and registers and
enables cd_AI without selecting it (the Rime user: which input source is in use stays the person's
choice). The input menu lists Compose and Continue, the current one ticked, as input methods list
their modes. The window has Hide and Window menus, remembers its place, opens links in the
browser, and keeps one instance with a real lock. The page opens with a one-use ticket instead of
the service token; a change the service cannot use is undone; setup ends in the settings.

## Open

- A release download (the owner's decision), with a checksum, and the Open Anyway picture.
- Done since: "Settings…" in the IBus and PIME menus; the Windows installer and the Linux script.
- What a local model needs on a typical Mac: the test VM (4 GB, 4 virtual cores) cannot hold
  Gemma 4 E4B, so "a model you run yourself" stays an advanced option, unmeasured there.
- A persistent mode indicator beyond the menu's tick (the Rime user); the CJK-style Enter (G47).

## Follow-up: when the service is down (three reviewers)

Asked whether compose should keep holding words (A), put them in as typed on a failure (B), or type
like a plain keyboard while the service is unreachable (C): the Rime user and the Mac input-method
developer chose A with a background check that says "offline" from the first key, as cloud input
methods grey out their cloud part (C changes the mode under your fingers, B commits what you did not
ask for); the product manager chose C but with held words kept, which is the same in practice. Done:
the worker checks /health every few seconds off the input thread; the panel says "cd_AI is offline"
with Shift+Enter to keep.

