# Releasing

A release happens when the reviewers' last round says ready (docs/research) and the owner agrees.
Round 3 (2026-10-24) left one blocker, for someone with an Anthropic API key (the maintainer agent has
none): on the Mac and on Windows, from downloaded release candidates,
- paste a funded key in the settings (it says Ready), log out (Mac) or restart (Windows), "ok" + Tab
  in TextEdit and Notepad: a Claude rewrite, with how long it took; screenshot both;
- paste a key from an account with no credit: the settings accept it, and "ok" + Tab says "no credit
  on your Anthropic account · console.anthropic.com"; screenshot it;
- paste a wrong key: the settings say "Anthropic did not accept that key";
- revoke the test keys. Then, in the release notes, replace @CLAUDE_TESTED@ with ", and from Claude".
The README and the site already point at `releases/latest` and the tag `v0.1.0`, so they work the
moment the release exists.

1. Tag the commit: `git tag v0.1.0 && git push origin v0.1.0` (the Linux script installs this tag;
   update `ref` in `scripts/install.sh` and the README and site lines for the next version).
2. On an Apple silicon Mac: `python3 platforms/macos/build.py && python3 platforms/macos/package.py`
   → `dist/macos/cd_AI.pkg`. Install it on a clean Mac (downloaded with Safari, so Gatekeeper sees
   it), log out, "ok" + Tab in TextEdit.
3. On Windows over cd_AI's PIME build (platforms/windows/pime): `python platforms\windows\package.py`
   → `dist\windows\cd_AI-setup.exe`. Install it on a clean Windows 11 (downloaded with Edge, Defender
   on), restart, "ok" + Tab in Notepad; uninstall, restart, Win+Space lists no cd_AI.
4. Checksums: `shasum -a 256 cd_AI.pkg cd_AI-setup.exe > SHA256SUMS`.
5. `gh release create v0.1.0 cd_AI.pkg cd_AI-setup.exe SHA256SUMS --title "cd_AI 0.1.0" --notes-file
   docs/release-notes-0.1.0.md` (what is tested and what is not: Intel Macs, Windows x64, Linux typing).
