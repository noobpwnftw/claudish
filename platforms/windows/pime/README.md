# Claudish's patched PIME

PIME's text service only changes the screen while answering a key or another event, and it
does not tell the input method what text surrounds the caret. Two small patches to PIME
(at `PIME_COMMIT`) and its libIME2 add both:

- **A timer:** a reply may say `"timer": ms`; the text service then calls back once
  (`onTimer`) in an asynchronous TSF edit session, and that reply updates the composition and
  candidates like a key's. cd_AI uses it to show an answer as soon as it arrives, instead of at
  your next key.
- **The text around the caret:** `onKeyDown`, `onKeyUp`, and `onTimer` requests carry
  `textBefore` and `textAfter` (up to 1,500 characters each, outside the composition), as IBus
  and InputMethodKit provide.

The Python side (`python/textService.py`) gains `setTimer(ms)`, `onTimer()`, and
`self.textBefore`/`self.textAfter`. The cd_AI adapter uses them when present and works as
before with a released PIME.

Build (in the Windows VM, see docs/development.md): `tests/desktop/windows/vm.sh pime`
prepares the patched source, then `vm.sh run tests/desktop/windows/jobs/build-pime.ps1 1400`
builds the text service for Win32, x64, and ARM64 with the Visual Studio 2022 C++ tools
(`jobs/buildtools.ps1` installs them) and installs it over the released PIME.

Upstream: the patches are kept here, not proposed upstream yet.
