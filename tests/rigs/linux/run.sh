#!/bin/sh
# Build separately; each check starts a disposable desktop and has a five-second limit.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../../.." && pwd)
image=claudish-linux-rig
case "${1:-}" in
  build) exec docker build -t "$image" "$here" ;;
  check)
    case "${2:-}" in
      compose|bypass|password|focus|offline) ;;
      *) echo "choose compose, bypass, password, focus, or offline" >&2; exit 2 ;;
    esac
    exec docker run --rm --network none --read-only --tmpfs /tmp \
      --tmpfs /home/tester:uid=1001,gid=1001 \
      -v "$root:/claudish:ro" "$image" \
      timeout 5 dbus-run-session -- python3 /claudish/tests/rigs/linux/driver.py "$2"
    ;;
  *) echo "usage: sh tests/rigs/linux/run.sh build | check SCENARIO" >&2; exit 2 ;;
esac
