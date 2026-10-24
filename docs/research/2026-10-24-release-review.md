# Release review for 0.1.0 (2026-10-24)

Five reviewers (a non-technical Mac writer, a Windows x64 user, a daily CJK input-method user, a
release engineer for unsigned desktop software, a consumer product manager) decided whether cd_AI is
ready for a first public release, over three rounds; each round's blockers were fixed or labelled.

- Round 1, all NOT READY. Fixed: Windows' PIME made a part of cd_AI (its own CLSID, folder, launcher
  pipe), installing beside any PIME and uninstalling cleanly (a libIME2 unregister bug fixed); the
  macOS package limited to Apple silicon (an arm64-only module); one honest status table; the
  download-first release text (branch agent/release-0.1.0); Windows offline and Defender checks.
  Found while checking: every HTTPS request from the macOS bundle failed certificate verification (no
  certificates in its OpenSSL), so Claude could never have worked on a Mac; fixed with certifi.
- Round 2, four NOT READY. Fixed: plain words for a key with no credit, a refused key, no key, rate
  limits and an overloaded API; SmartScreen on a downloaded installer checked (Run anyway shown;
  Smart App Control in evaluation did not block); the x64 Python's packages checked under emulation.
- Round 3, all NOT READY on one blocker only: a rewrite through Claude with a valid Anthropic API key,
  which only the owner can run. docs/release.md has the check list; docs/release-notes-0.1.0.md (on
  the release branch) says what is and is not tested, as the reviewers asked.
