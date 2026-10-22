#!/bin/sh
# Build the image once, then run the real-desktop IBus scenarios against this checkout.
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
docker build -q -t claudish-desktop-linux "$here" >/dev/null
exec docker run --rm --network none -v "$root:/claudish:ro" claudish-desktop-linux \
  dbus-run-session -- python3 /claudish/tests/desktop/linux/driver.py
