"""The Compose key's sequences (Compose o c is ©), from the X11 compose table GTK and IBus's own
simple engine read: the user's ~/.XCompose (or $XCOMPOSEFILE) over the locale's system table."""
import os
import re
from pathlib import Path

# <Multi_key> <o> <c> : "©" copyright, or a keysym alone: <Multi_key> <period> <period> : ellipsis
LINE = re.compile(r'^\s*((?:<[^>]+>\s*)+):\s*(?:"((?:[^"\\]|\\.)*)"|(\w+))')
INCLUDE = re.compile(r'^\s*include\s+"([^"]*)"')
SYSTEM_DIR = "/usr/share/X11/locale"
SYSTEM = (SYSTEM_DIR + "/en_US.UTF-8/Compose", "/usr/X11R6/lib/X11/locale/en_US.UTF-8/Compose")
ESCAPES = {"n": b"\n", "r": b"\r", "t": b"\t"}


def unescape(text):
    """A quoted result, as libX11 reads it: \\" and \\\\, octal and hex bytes (UTF-8), \\n."""
    out, at = bytearray(), 0
    while at < len(text):
        char = text[at]
        if char != "\\" or at + 1 == len(text):
            out += char.encode("utf-8")
            at += 1
            continue
        octal = re.match(r"[0-7]{1,3}", text[at + 1:])
        hexa = re.match(r"[xX]([0-9A-Fa-f]{1,2})", text[at + 1:])
        if octal:
            out.append(int(octal.group(), 8) & 0xFF)
            at += 1 + len(octal.group())
        elif hexa:
            out.append(int(hexa.group(1), 16))
            at += 1 + len(hexa.group())
        else:
            out += ESCAPES.get(text[at + 1], text[at + 1].encode("utf-8"))
            at += 2
    return out.decode("utf-8", errors="replace")


def system_file():
    return next((path for path in SYSTEM if os.path.isfile(path)), SYSTEM[0])


def read(path, table, replace=False, depth=0):
    """Add a file's Compose-key sequences to table (key names tuple -> text, or ("keysym", name)).
    replace: a later file's, which replace the ones they conflict with (one a prefix of the other),
    as libX11 does."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        included = INCLUDE.match(line)
        if included and depth < 4:
            target = included.group(1).replace("%%", "\0").replace("%H", os.path.expanduser("~")) \
                .replace("%L", system_file()).replace("%S", SYSTEM_DIR).replace("\0", "%")
            if os.path.abspath(target) != os.path.abspath(system_file()) or not replace:
                read(target, table, replace, depth + 1)  # the system table is read already
            continue
        found = LINE.match(line)
        if not found:
            continue
        keys = tuple(re.findall(r"<([^>]+)>", found.group(1)))
        if len(keys) < 2 or keys[0] != "Multi_key":
            continue
        keys = keys[1:]
        if replace:
            for other in [k for k in table if k[:len(keys)] == keys or keys[:len(k)] == k]:
                del table[other]
        table[keys] = unescape(found.group(2)) if found.group(2) is not None else ("keysym", found.group(3))


def load():
    table = {}
    read(system_file(), table)
    read(os.environ.get("XCOMPOSEFILE") or os.path.expanduser("~/.XCompose"), table, replace=True)
    return table


def unicode_name(name):
    """<U01A1> (any case, as the files write it): the character, else None."""
    found = re.fullmatch(r"[Uu]\+?([0-9A-Fa-f]{2,6})", name)
    return chr(int(found.group(1), 16)) if found and int(found.group(1), 16) <= 0x10FFFF else None


class Compose:
    """What follows the Compose key, key by key: the text a sequence makes, or that it goes on.
    key(name): what a key name in the files is compared as (the engine's: the character the key
    types, else its keyval; None when it names no key)."""
    def __init__(self, table=None, key=lambda name: name):
        def compared(name):
            return unicode_name(name) or key(name)
        self.table = {}
        for names, text in (load() if table is None else table).items():
            keys = tuple(compared(name) for name in names)
            if isinstance(text, tuple):  # a keysym's own character
                text = compared(text[1])
                if not isinstance(text, str):
                    continue
            if None not in keys:
                self.table[keys] = text
        self.prefixes = {keys[:n] for keys in self.table for n in range(1, len(keys))}

    def step(self, keys):
        """("text", what it makes), ("wait", None) while it can go on, or ("none", None)."""
        keys = tuple(keys)
        if keys in self.table:
            return "text", self.table[keys]
        return ("wait", None) if keys in self.prefixes else ("none", None)
