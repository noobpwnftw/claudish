#!/bin/sh
# cd_AI on Linux in one line (G61), until there are packages:
#   curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/main/scripts/install.sh | sh
# It clones (or updates) cd_AI into ~/.local/share/claudish, makes its own Python environment there,
# and runs `claudish setup`, which asks before each step and ends in cd_AI's settings (your key,
# the tone). Nothing here uses sudo: a missing system package is named, with the line to install it.
set -e
home=${CLAUDISH_HOME:-$HOME/.local/share/claudish}

missing=""
command -v git > /dev/null || missing="$missing git"
command -v python3 > /dev/null || missing="$missing python3"
python3 -c "import venv, ensurepip" 2> /dev/null || missing="$missing python3-venv"
/usr/bin/python3 -c "import gi; gi.require_version('IBus', '1.0')" 2> /dev/null || missing="$missing ibus python3-gi gir1.2-ibus-1.0"
if [ -n "$missing" ]; then
  echo "cd_AI needs:$missing"
  echo "On Ubuntu or Debian: sudo apt install$missing   (then run this again)"
  exit 1
fi

if [ -d "$home/.git" ]; then
  git -C "$home" pull --ff-only --quiet
else
  git clone --quiet "${CLAUDISH_REPO:-https://github.com/noobpwnftw/claudish}" "$home"
fi
cd "$home"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[claude]"
echo "cd_AI is in $home. Setting it up:"
# setup asks questions: read them from the terminal even when this script came through a pipe.
if [ -t 0 ]; then
  exec .venv/bin/python -m claudish setup
elif (: < /dev/tty) 2> /dev/null; then  # a terminal to ask in (it can exist and not open)
  exec .venv/bin/python -m claudish setup < /dev/tty
else
  exec .venv/bin/python -m claudish setup --yes
fi
