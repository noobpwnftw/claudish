#!/bin/sh
# Screenshots of every state cd_AI shows in Notepad on Windows (the visual pass, G45): runs
# jobs/gallery.ps1 in the VM and captures the screen each time it announces a state.
here=$(cd "$(dirname "$0")" && pwd); vm=${CLAUDISH_VM:-$HOME/vm/claudish-windows}
out=${1:-$here/../../../.tools/gallery/windows}; mkdir -p "$out"
rm -f "$vm/shared/results/gallery-state.txt" "$vm/shared/results/gallery-ack.txt"
"$here/vm.sh" run "$here/jobs/gallery.ps1" 120 >/dev/null 2>&1 &
last=""
for i in $(seq 600); do
  now=$( (tr -d '\r\n\377\376\000' < "$vm/shared/results/gallery-state.txt") 2>/dev/null)
  if [ -n "$now" ] && [ "$now" != "$last" ]; then
    [ "$now" = done ] && break
    "$here/vmscreen.sh" "$out/$now.png" && echo "captured $now"
    echo ok > "$vm/shared/results/gallery-ack.txt"; last=$now
  fi
  sleep 0.2
done
wait
