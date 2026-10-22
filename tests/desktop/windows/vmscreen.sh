#!/bin/sh
# Optionally send QEMU monitor commands (args), wait a second, and save the VM screen as PNG.
# usage: vmscreen.sh OUT.png ['sendkey alt-tab' ...]   (about 1-2 s in total)
out=$1; shift
{ for cmd in "$@"; do echo "$cmd"; done; } | docker exec -i claudish-windows sh -c 'nc -U -q 1 /run/shm/monitor.sock >/dev/null'
[ $# -gt 0 ] && sleep 1
echo 'screendump /tmp/screen.png -f png' | docker exec -i claudish-windows sh -c 'nc -U -q 1 /run/shm/monitor.sock >/dev/null'
docker cp -q claudish-windows:/tmp/screen.png "$out"
