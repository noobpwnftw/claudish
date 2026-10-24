# Releasing

A release happens when the reviewers' last round says ready (docs/research) and the owner agrees.
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
5. `gh release create v0.1.0 cd_AI.pkg cd_AI-setup.exe SHA256SUMS --title "cd_AI 0.1.0"`, with notes
   saying what is tested and what is not (Intel Macs, Windows x64, Linux typing).
