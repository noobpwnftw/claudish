#!/bin/sh
# Screenshots of cd_AI on macOS, named by the design lab's state ids: gallery.py types the states into
# the rig's test app; with a second argument "preview", platforms/macos/panel_preview.py draws every
# lab state with the native panel instead. Runs on the
# Mac VM over SSH and captures its screen over VNC (vncdotool) each time it announces a state.
# CLAUDISH_MAC (ssh target), CLAUDISH_MAC_KEY, CLAUDISH_VNC_USER/PASSWORD, VNCDO (vncdo program).
here=$(cd "$(dirname "$0")" && pwd)
mac=${CLAUDISH_MAC:-claudish@10.0.0.251}; key=${CLAUDISH_MAC_KEY:-$HOME/.ssh/claudish_mac_vm}
out=${1:-$here/../../../.tools/gallery/macos}; mkdir -p "$out"
script=tests/desktop/macos/gallery.py
[ "$2" = preview ] && script=platforms/macos/panel_preview.py
remote() { ssh -i "$key" -o ConnectTimeout=5 "$mac" "$@"; }
remote 'rm -f /tmp/claudish-gallery-state /tmp/claudish-gallery-ack; cd ~/claudish &&
  (.tools/macos-build-venv/bin/python '"$script"' >/tmp/claudish-gallery.log 2>&1 &)'
last=""
for i in $(seq 300); do
  now=$(remote 'cat /tmp/claudish-gallery-state 2>/dev/null')
  if [ -n "$now" ] && [ "$now" != "$last" ]; then
    [ "$now" = done ] && break
    "${VNCDO:-vncdo}" -s "${mac#*@}::5900" --username "${CLAUDISH_VNC_USER:-claudish}" -p "$CLAUDISH_VNC_PASSWORD" \
      capture "$out/$now.png" 2>/dev/null && echo "captured $now"
    remote 'touch /tmp/claudish-gallery-ack'; last=$now
  fi
  sleep 0.3
done
