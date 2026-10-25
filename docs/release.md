# Releasing

The 0.1.0 preparation stays on `agent/release-0.1.0` until the checks below are complete and the
owner approves publishing. Its download links and Linux `v0.1.0` installer reference are intended
for publication together; do not merge them to the live site before the release exists.

## Candidate evidence

The current candidates are from `926e0bc`, kept locally in `dist/candidates/926e0bc/` with their
SHA-256 hashes and checks in `manifest.json`:

| File | SHA-256 |
| --- | --- |
| `cd_AI.pkg` | `395ae3a94ee233194e097b4448aae9a59c0a0432e81dfcf13d19f53cf1598c41` |
| `cd_AI-setup.exe` | `96e181122e8bad22cd7f5e6b2853a5e905a0473208878ab8a1a7981ae991792b` |

The macOS package was installed on the VM and checked after reboot (doctor, the service at login,
MCP tools); the owner hand-tested the day's builds. The Windows installer was installed the way a
double-click does, by a standard account with an administrator's password, and its service started
at login after a restart. Browser-download installs remain unchecked for these candidates.
[Development](development.md#current-evidence-and-next-checks) records the wider checks.

## Before publication

1. Integrate current main into the preparation branch. Run `python scripts/check.py` on the
   proposed source. Build the packages on their respective VMs:
   `python3 platforms/macos/build.py && python3 platforms/macos/package.py` produces
   `dist/macos/cd_AI.pkg`; on Windows, `python platforms\windows\package.py` over cd_AI's PIME
   build produces `dist\windows\cd_AI-setup.exe`. Record their source commit and hashes.
2. Install the candidates on the VMs: a new account on macOS, a standard account on Windows (the
   way a double-click does, an administrator's password at UAC). Choose a model in Settings, try a
   rewrite, log out/in or restart, then type `ok`, Tab, Tab in TextEdit and Notepad. x64 Windows
   remains untested; keep that limit in the release notes.
3. Not before this release: signing and notarization (the source is published; signing comes with
   traction), and a funded Anthropic API key (most users choose a subscription; an API-key problem
   comes back as a bug report).
4. Verify the Linux installer in a clean Docker rig against the proposed source, using
   `CLAUDISH_REF` to select it before the tag exists. At publication, its default reference and
   every installation snippet must match `v0.1.0`.
5. Write the release notes as what the release does and supports, with no tested-on, verified or
   preview claims (owner: a problem comes back as a report); no draft notice; the changelog heading
   as the version. Ask the owner to approve the exact commit, the two
   package hashes and the notes.
6. After publication: download the published files with Safari and Edge, check their hashes, and
   install the published `.pkg` on a fresh macOS account through to a first accepted rewrite.

## Publication, after approval

Tag the approved source with `git tag v0.1.0 && git push origin v0.1.0`, then publish the two
approved files with `gh release create v0.1.0 cd_AI.pkg cd_AI-setup.exe --title "cd_AI 0.1.0"
--notes-file docs/release-notes-0.1.0.md`. Use the actual file paths. Merge the prepared download
instructions to main and check that the release links and the tagged Linux installer resolve.
For the next release, update the installer reference and the README, install guide and site
snippets together.
