# Releasing

A release `vX.Y.Z` is prepared on an `agent/release-X.Y.Z` branch and published only after the
owner approves it. Candidates and what was checked on each are kept locally in
`dist/candidates/<commit>/` with their SHA-256 hashes in `manifest.json`.

## Before publication

1. Set the version everywhere it appears: `pyproject.toml`, `platforms/linux/install.py`,
   `platforms/macos/setup.py` and `Info.plist` (with its build number),
   `platforms/windows/claudish/ime.json`, the `CLAUDISH_REF` default in `scripts/install.sh`, and
   the Linux one-liner in the README, `docs/install.md` and `site/index.html`. Add the changelog
   entry and `docs/release-notes-X.Y.Z.md`.
2. Run `python scripts/check.py` on the proposed source. Build the packages on their respective
   VMs: `python3 platforms/macos/build.py && python3 platforms/macos/package.py` produces
   `dist/macos/cd_AI.pkg`; on Windows, `python platforms\windows\package.py` over cd_AI's PIME
   build produces `dist\windows\cd_AI-setup.exe`. Record their source commit and hashes.
3. Install the candidates on the VMs: a new account on macOS, a standard account on Windows (the
   way a double-click does, an administrator's password at UAC). Choose a model in Settings, try a
   rewrite, log out/in or restart, then type `ok`, Tab, Tab in TextEdit and Notepad.
4. Not part of a release yet: signing and notarization (the source is published; signing comes
   with traction), and a funded Anthropic API key (most users choose a subscription; an API-key
   problem comes back as a bug report).
5. Check the Linux installer in a clean Docker rig against the proposed source, using
   `CLAUDISH_REF` to select it before the tag exists.
6. Write the release notes as what the release does and supports, with no tested-on, verified or
   preview claims (owner: a problem comes back as a report); no draft notice; the changelog heading
   as the version. Ask the owner to approve the exact commit, the two package hashes and the notes.

## Publication, after approval

Tag the approved source with `git tag vX.Y.Z && git push origin vX.Y.Z`, then publish the two
approved files with `gh release create vX.Y.Z cd_AI.pkg cd_AI-setup.exe --title "cd_AI X.Y.Z"
--notes-file docs/release-notes-X.Y.Z.md`. Use the actual file paths. Merge the release branch to
main and check that the release links and the tagged Linux installer resolve.

After publication: download the published files with Safari and Edge, check their hashes, and
install the published `.pkg` on a fresh macOS account through to a first accepted rewrite.
