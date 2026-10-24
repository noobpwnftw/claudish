#!/bin/sh
# One macOS test cycle, on the Mac: build, install cd_AI.pkg over whatever is installed, run the rig,
# and leave cd_AI installed as a user's would be. Nothing stale: the package's postinstall stops the
# old build. Nothing colliding: for the run, the login service gives the port to the same bundle's
# rules service (the rig's deterministic backend), and gets it back afterwards.
# tests/desktop/macos/cycle.sh [driver arguments]; the log ends with "cycle exit N".
cd "$(dirname "$0")/../../.." || exit 1
python=.tools/macos-build-venv/bin/python
domain=gui/$(id -u)
agent=$HOME/Library/LaunchAgents/com.claudish.service.plist
cd_ai="$HOME/Library/Input Methods/Claudish.app/Contents/MacOS/Claudish"
port=18765
finish() { echo "cycle exit $1"; exit "$1"; }

echo "== build"
$python platforms/macos/build.py > /tmp/claudish-build.log 2>&1 || { tail -5 /tmp/claudish-build.log; finish 1; }
$python platforms/macos/package.py > /tmp/claudish-package.log 2>&1 || { tail -5 /tmp/claudish-package.log; finish 1; }
echo "== install"
installer -pkg dist/macos/cd_AI.pkg -target CurrentUserHomeDirectory 2>&1 | tail -1

echo "== rules service"
launchctl bootout "$domain/com.claudish.service" 2> /dev/null
for pid in $(lsof -tiTCP:$port -sTCP:LISTEN); do kill "$pid"; done  # a leftover service of any build
for i in 1 2 3 4 5; do lsof -tiTCP:$port -sTCP:LISTEN > /dev/null || break; sleep 1; done
"$cd_ai" serve --backend rules --port $port > /tmp/claudish-rules.log 2>&1 < /dev/null &
rules=$!
for i in $(seq 20); do curl -s -m 1 127.0.0.1:$port/health > /dev/null && break; sleep 0.5; done
curl -s -m 1 127.0.0.1:$port/health > /dev/null || { tail -5 /tmp/claudish-rules.log; kill $rules; launchctl bootstrap "$domain" "$agent"; finish 1; }

echo "== rig"
$python tests/desktop/macos/driver.py "$@"
status=$?

kill $rules; wait $rules 2> /dev/null
launchctl bootstrap "$domain" "$agent"  # the login service again, as installed
launchctl print "$domain/com.claudish.service" | grep -m1 "state ="
finish $status
