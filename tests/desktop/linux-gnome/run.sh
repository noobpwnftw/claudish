#!/bin/sh
# GNOME Shell on Wayland (headless) with IBus and the Claudish engine, in a systemd container.
set -e
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
docker build -q -t claudish-gnome "$here" >/dev/null
id=$(docker run -d --rm --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run --tmpfs /run/lock \
     -v "$root:/claudish:ro" claudish-gnome)
trap 'docker stop -t 5 "$id" >/dev/null' EXIT
user() { docker exec -u tester -e XDG_RUNTIME_DIR=/run/user/1001 -e DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus \
         -e WAYLAND_DISPLAY=wayland-0 -w /home/tester "$id" "$@"; }
for i in $(seq 60); do docker exec "$id" test -S /run/user/1001/bus 2>/dev/null && break; sleep 0.5; done
user python3 /claudish/platforms/linux/install.py >/dev/null
user gsettings set org.gnome.desktop.input-sources sources "[('ibus', 'claudish')]"
user gsettings set org.gnome.shell disable-extension-version-validation true
# A login would load install.py's environment.d file; GNOME Shell starts ibus-daemon with it.
user sh -c 'set -a; . ~/.config/environment.d/90-claudish-ibus.conf; set +a;
  nohup gnome-shell --headless --unsafe-mode --wayland --virtual-monitor 1280x800 >/tmp/gnome-shell.log 2>&1 &'
for i in $(seq 60); do user test -S /run/user/1001/wayland-0 2>/dev/null && break; sleep 0.5; done
for i in $(seq 60); do user ibus list-engine 2>/dev/null | grep -q claudish && break; sleep 0.5; done
user python3 /claudish/tests/desktop/linux-gnome/driver.py || { user tail -20 /tmp/gnome-shell.log; exit 1; }
