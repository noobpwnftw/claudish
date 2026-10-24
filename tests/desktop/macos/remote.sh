#!/bin/sh
# Run cycle.sh on the Mac from here: this working tree (uncommitted changes too) is synced to
# ~/claudish there, the cycle runs detached (a dropped connection does not stop it half way), and
# its log is followed until it ends. Exits with the cycle's status.
# CLAUDISH_MAC (ssh target), CLAUDISH_MAC_KEY. Arguments go to driver.py.
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
mac=${CLAUDISH_MAC:-claudish@10.0.0.251}; key=${CLAUDISH_MAC_KEY:-$HOME/.ssh/claudish_mac_vm}
remote() { timeout 15 ssh -n -i "$key" -o ConnectTimeout=5 "$mac" "$@"; }
log=/tmp/claudish-cycle.log

cd "$root" && git ls-files -z -co --exclude-standard | xargs -0 tar czf /tmp/claudish-sync.tgz --ignore-failed-read 2> /dev/null
scp -q -i "$key" -o ConnectTimeout=5 /tmp/claudish-sync.tgz "$mac:/tmp/claudish-sync.tgz" || exit 1
remote "mkdir -p ~/claudish && tar xzf /tmp/claudish-sync.tgz -C ~/claudish && rm -f $log &&
  (nohup sh ~/claudish/tests/desktop/macos/cycle.sh $* > $log 2>&1 < /dev/null &)" || exit 1
shown=0
while :; do
  sleep 3
  lines=$(remote "cat $log" 2> /dev/null) || continue
  echo "$lines" | tail -n +$((shown + 1))
  shown=$(echo "$lines" | wc -l)
  status=$(echo "$lines" | sed -n 's/^cycle exit //p')
  [ -n "$status" ] && exit "$status"
done
