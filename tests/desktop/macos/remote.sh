#!/bin/sh
# Run a whole macOS cycle on the Mac from here: this working tree (uncommitted changes too) is synced
# to ~/claudish there, `cycle.sh install` runs, the Mac restarts (the logout an installed input
# method needs; the test Mac logs in by itself and has passwordless sudo), and `cycle.sh test` runs
# once its desktop is back. Each phase runs detached, so a dropped connection does not stop it half
# way; its log is followed here. Exits with the test phase's status.
# CLAUDISH_MAC (ssh target), CLAUDISH_MAC_KEY. Arguments go to driver.py.
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
mac=${CLAUDISH_MAC:-claudish@10.0.0.251}; key=${CLAUDISH_MAC_KEY:-$HOME/.ssh/claudish_mac_vm}
remote() { timeout 15 ssh -n -i "$key" -o ConnectTimeout=5 "$mac" "$@"; }
log=/tmp/claudish-cycle.log

phase() {  # phase NAME [args]: start it detached, follow its log, return its status
  remote "rm -f $log && (nohup sh ~/claudish/tests/desktop/macos/cycle.sh $* > $log 2>&1 < /dev/null &)" || return 1
  shown=0
  while :; do
    sleep 3
    lines=$(remote "cat $log" 2> /dev/null) || continue
    echo "$lines" | tail -n +$((shown + 1))
    shown=$(echo "$lines" | wc -l)
    status=$(echo "$lines" | sed -n 's/^cycle exit //p')
    [ -n "$status" ] && return "$status"
  done
}

cd "$root" && git ls-files -z -co --exclude-standard | xargs -0 tar czf /tmp/claudish-sync.tgz --ignore-failed-read 2> /dev/null
scp -q -i "$key" -o ConnectTimeout=5 /tmp/claudish-sync.tgz "$mac:/tmp/claudish-sync.tgz" || exit 1
remote "mkdir -p ~/claudish && tar xzf /tmp/claudish-sync.tgz -C ~/claudish" || exit 1
phase install || exit 1

echo "== restart (the logout an installed input method needs)"
remote "sudo shutdown -r now" > /dev/null 2>&1
sleep 20
for i in $(seq 60); do  # back, and logged in: the Dock runs in the desktop session
  remote "pgrep -x Dock" > /dev/null 2>&1 && break
  sleep 5
done
remote "pgrep -x Dock" > /dev/null 2>&1 || { echo "the Mac did not come back with a desktop"; exit 1; }
# A fresh login keeps the Mac busy for a minute or two (the load average reached 25), and an input
# method loading then misses the first keys: wait for it to settle.
for i in $(seq 36); do
  load=$(remote "sysctl -n vm.loadavg" 2> /dev/null | awk '{print int($2)}')
  [ -n "$load" ] && [ "$load" -lt 3 ] && break
  sleep 5
done
phase test "$@"
