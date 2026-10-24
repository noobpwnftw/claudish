# Claudish's PIME

cd_AI on Windows runs only on Claudish's own build of PIME: PIME (at `PIME_COMMIT`) and its
libIME2 with the patches here. A released PIME is not supported. The patches add:

- **A timer:** a reply may say `"timer": ms`; the text service then calls back once
  (`onTimer`) in an asynchronous TSF edit session, and that reply updates the composition and
  candidates like a key's. cd_AI shows an answer as soon as it arrives, not at your next key.
- **The text around the caret:** `onKeyDown`, `onKeyUp`, and `onTimer` requests carry
  `textBefore` and `textAfter` (up to 1,500 characters each, outside the composition), as IBus
  and InputMethodKit provide.
- **cd_AI's candidate window** (libIME2 `CandidateWindow`, `Style.h`): a header (a question as
  is; `"label\nbody"` adds a small label) and a footer (the one short hint, or what is
  happening) around the items (`candidateHeader`, `candidateFooter`; Python
  `setCandidateHeader`/`setCandidateFooter`), so nothing shows in a passing notice; one column,
  long items wrapped, selection keys muted (a space key shows none), the highlighted row as a soft
  fill with an accent bar, the app theme's light or dark colours, Windows 11's rounded corners
  and shadow. The message window has the same look.

The Python side (`python/textService.py`) gains `setTimer(ms)`, `onTimer()`,
`self.textBefore`/`self.textAfter`, and the header and footer.

Build: `make_source.sh OUT.zip` prepares the patched source; on Windows, `build-pime.ps1` builds
the text service for Win32, x64, and ARM64 with the Visual Studio 2022 C++ tools
(`buildtools.ps1` installs them) and installs it over PIME's released files.

Upstream: the patches are kept here, not proposed upstream yet.
