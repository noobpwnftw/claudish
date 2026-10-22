#!/bin/sh
# Windows 11 on ARM (Enterprise evaluation) under qemu/KVM via dockur, for TSF/PIME tests.
# State lives in $CLAUDISH_VM (default ~/vm/claudish-windows); jobs/results in $CLAUDISH_VM/shared.
set -e
here=$(cd "$(dirname "$0")" && pwd)
vm=${CLAUDISH_VM:-$HOME/vm/claudish-windows}
mkdir -p "$vm/storage" "$vm/shared"
case "$1" in
  start)
    # Copy, never bind the working tree: a branch switch would leave the VM an empty folder.
    rm -rf "$vm/oem" && cp -r "$here/oem" "$vm/oem"
    docker run -d --name claudish-windows --device /dev/kvm --device /dev/net/tun --cap-add NET_ADMIN \
      -e VERSION=11e -e RAM_SIZE=8G -e CPU_CORES=6 -e DISK_SIZE=64G \
      -p 127.0.0.1:8006:8006 -v "$vm/storage:/storage" -v "$vm/shared:/shared" -v "$vm/oem:/oem:ro" \
      --stop-timeout 120 dockurr/windows-arm:latest ;;
  stop) docker stop claudish-windows && docker rm claudish-windows ;;
  logs) docker logs --tail 30 claudish-windows ;;
  sync)  # Copy the committed checkout into the shared folder for jobs to unpack.
    git -C "$here/../../.." archive --format=zip -o "$vm/shared/claudish.zip" HEAD && echo "synced $(git -C "$here/../../.." rev-parse --short HEAD)" ;;
  bootstrap)  # Start the job runner by typing into the VM, if the OEM hook did not run.
    mkdir -p "$vm/shared/oem" && cp "$here"/oem/* "$vm/shared/oem/"
    python3 "$here/vmkeys.py" 'New-Item -ItemType Directory -Force C:\OEM; Copy-Item \\host.lan\Data\oem\* C:\OEM; cmd /c C:\OEM\install.bat' --enter ;;
  run)  # Run a job script in the VM's desktop session and print its output.
    name=$(basename "$2" .ps1); rm -f "$vm/shared/results/$name.txt"
    cp "$2" "$vm/shared/jobs/$name.ps1"
    while [ ! -f "$vm/shared/results/$name.txt" ]; do sleep 2; done
    cat "$vm/shared/results/$name.txt" ;;
  *) echo "usage: $0 start|stop|logs|sync|bootstrap|run JOB.ps1" >&2; exit 2 ;;
esac
