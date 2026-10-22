#!/bin/sh
# Install, autostart (user manager restart = new login), and uninstall the systemd user unit, in a container.
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
docker build -q -t claudish-systemd "$here" >/dev/null
id=$(docker run -d --rm --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run --tmpfs /run/lock \
     -v "$root:/claudish:ro" claudish-systemd)
trap 'docker stop -t 5 "$id" >/dev/null' EXIT
as_tester() { docker exec -u tester -e XDG_RUNTIME_DIR=/run/user/1001 -e DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus -w /claudish "$id" "$@"; }
health() { as_tester python3 -c "
import json, time, urllib.request
for _ in range(40):
    try: print(json.load(urllib.request.urlopen('http://127.0.0.1:18765/health', timeout=1))['backend']); break
    except Exception: time.sleep(0.25)
else: print('down')"; }
for i in $(seq 60); do docker exec "$id" test -S /run/user/1001/bus 2>/dev/null && break; sleep 0.5; done
echo "before: $(health)"
as_tester python3 -m claudish service install --serve -- --backend rules
echo "after install: $(health)"
docker exec "$id" systemctl restart user@1001.service   # a fresh login session for the user
for i in $(seq 40); do docker exec "$id" test -S /run/user/1001/bus 2>/dev/null && break; sleep 0.25; done
echo "after a new login (user manager restarted): $(health)"
as_tester python3 -m claudish doctor | grep -E "Service|Starts at login" || true
as_tester python3 -m claudish service uninstall
echo "after uninstall: $(health)"
as_tester sh -c 'ls ~/.config/systemd/user/claudish.service 2>/dev/null || echo "unit removed"'
