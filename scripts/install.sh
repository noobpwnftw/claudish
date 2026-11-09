#!/bin/sh
# cd_AI on Linux in one line, until there are packages:
#   curl -fsSL https://raw.githubusercontent.com/noobpwnftw/claudish/v0.4.3/scripts/install.sh | sh
# It clones (or updates) cd_AI into ~/.local/share/claudish, makes its own Python environment there,
# and runs `claudish setup`, which ends in cd_AI's settings (the key, the tone). A missing system
# package is named, with the line to install it.
set -e
if [ "$(id -u)" = 0 ]; then  # sudo: it would all go to root's home, not your session's
  echo "Run this as yourself, without sudo: cd_AI installs into your own home and session."
  exit 1
fi
home=${CLAUDISH_HOME:-$HOME/.local/share/claudish}
ref=${CLAUDISH_REF:-v0.4.3}  # the release this script belongs to

missing=""
command -v git > /dev/null || missing="$missing git"
command -v python3 > /dev/null || missing="$missing python3"
python3 -c "import venv, ensurepip" 2> /dev/null || missing="$missing python3-venv"
for python in python3 /usr/bin/python3; do  # cd_AI's environment, and the input method's (the system's)
  if command -v "$python" > /dev/null && ! "$python" -c "import sys; sys.exit(sys.version_info < (3, 10))"; then
    echo "cd_AI needs Python 3.10 or newer; $python is $("$python" -c 'import platform; print(platform.python_version())')."
    echo "Ubuntu 22.04, Debian 12, Fedora 36 and later have it."
    exit 1
  fi
done
/usr/bin/python3 -c "import gi; gi.require_version('IBus', '1.0')" 2> /dev/null || missing="$missing ibus python3-gi gir1.2-ibus-1.0"
if [ -n "$missing" ]; then
  echo "cd_AI needs:$missing"
  echo "On Ubuntu or Debian: sudo apt install$missing   (then run this again)"
  exit 1
fi

if [ -d "$home/.git" ]; then
  git -C "$home" fetch --quiet --tags origin  # each its own command: set -e stops at either
  git -C "$home" checkout --quiet "$ref"
  # A branch (CLAUDISH_REF=main) moves to what was fetched; a tag is where it is.
  if git -C "$home" show-ref --verify --quiet "refs/remotes/origin/$ref"; then
    git -C "$home" merge --ff-only --quiet "origin/$ref"
  fi
else
  git clone --quiet --branch "$ref" "${CLAUDISH_REPO:-https://github.com/noobpwnftw/claudish}" "$home"
fi
cd "$home"
# Made again when the system Python it was made with has gone (an upgrade from 3.12 to 3.13).
.venv/bin/python -c "import pip" 2> /dev/null || python3 -m venv --clear .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[claude,mcp]"
# `claudish` on PATH, as ~/.local/bin is on Ubuntu, Fedora and most desktops.
mkdir -p "$HOME/.local/bin"
ln -sf "$home/.venv/bin/claudish" "$HOME/.local/bin/claudish"
# An update: the running service restarts with the new code (setup leaves a running one alone).
if [ -f "$HOME/.config/systemd/user/claudish.service" ]; then  # where systemd reads it (claudish service)
  .venv/bin/python -m claudish service install > /dev/null && echo "cd_AI's service restarted with this version."
  # The input method and the GNOME extension run in your session: they load the new code at login.
  echo "Log out and back in to type with this version."
fi
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "The claudish command is in ~/.local/bin, which is not on PATH in this shell; a new login adds it on most desktops." ;;
esac
echo "cd_AI is in $home. Setting it up:"
# setup asks questions: read them from the terminal even when this script came through a pipe.
if [ -t 0 ]; then
  exec .venv/bin/python -m claudish setup
elif (: < /dev/tty) 2> /dev/null; then  # a terminal to ask in (it can exist and not open)
  exec .venv/bin/python -m claudish setup < /dev/tty
else
  exec .venv/bin/python -m claudish setup --yes
fi
