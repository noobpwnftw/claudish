#!/bin/sh
# PIME (EasyIME/PIME) at the pinned commit with Claudish's patches applied, zipped for a Windows
# build (build-pime.ps1, beside this file, on Windows). Usage: make_source.sh OUT.zip
set -e
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
work="$root/.tools/pime-src"
commit=$(cat "$here/PIME_COMMIT")
[ -d "$work/.git" ] || git clone -q https://github.com/EasyIME/PIME.git "$work"
git -C "$work" fetch -q origin "$commit" 2>/dev/null || true
git -C "$work" checkout -q -f "$commit"
git -C "$work" clean -qfdx -e libIME2
git -C "$work" submodule update -q --init libIME2
git -C "$work/libIME2" reset -q && git -C "$work/libIME2" checkout -q -f . && git -C "$work/libIME2" clean -qfdx
git -C "$work" apply "$here/pime.patch"
git -C "$work/libIME2" apply "$here/libime2.patch"
# The launcher is built by build-pime.ps1 with cargo (its own pipe and names, a static runtime), not
# through CMake: drop CMake's x86-only launcher block, which needs Rust and git.
python3 - "$work/CMakeLists.txt" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path).read()
text = re.sub(r'# only build the following components for 32-bit x86 platform.*?endif\("\$\{CMAKE_SIZEOF_VOID_P\}" EQUAL "4"\)\n',
              '', text, flags=re.S)
open(path, "w").write(text)
PY
rm -f "$1"
(cd "$work" && zip -qr "$1" CMakeLists.txt version.txt PIMETextService PIMELauncher libIME2 json python/textService.py \
  -x '*/.git/*' 'PIMELauncher/target/*' 'PIMELauncher/cargo_check.log')
echo "PIME $(echo "$commit" | cut -c1-7) + patches -> $1"
