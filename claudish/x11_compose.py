"""The Compose key's sequences (Compose o c is ©), from the X11 compose table GTK and IBus's own
simple engine read: the user's ~/.XCompose (or $XCOMPOSEFILE) over the locale's system table."""
import os
import re
from pathlib import Path

# <Multi_key> <o> <c> : "©" copyright
LINE = re.compile(r'^\s*((?:<[^>]+>\s*)+):\s*"((?:[^"\\]|\\.)*)"')
SYSTEM = ("/usr/share/X11/locale/en_US.UTF-8/Compose", "/usr/X11R6/lib/X11/locale/en_US.UTF-8/Compose")


def unescape(text):
    return re.sub(r'\\(.)', r'\1', text)


def read(path, table):
    """Add a file's Compose-key sequences to table (key names tuple -> text)."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        found = LINE.match(line)
        if found:
            keys = tuple(re.findall(r"<([^>]+)>", found.group(1)))
            if len(keys) > 1 and keys[0] == "Multi_key":
                table[keys[1:]] = unescape(found.group(2))


def load():
    table = {}
    read(next((path for path in SYSTEM if os.path.isfile(path)), SYSTEM[0]), table)
    read(os.environ.get("XCOMPOSEFILE") or os.path.expanduser("~/.XCompose"), table)
    return table


class Compose:
    """What follows the Compose key, key by key: the text a sequence makes, or that it goes on."""
    def __init__(self, table=None):
        self.table = load() if table is None else table
        self.prefixes = {keys[:n] for keys in self.table for n in range(1, len(keys))}

    def step(self, keys):
        """("text", what it makes), ("wait", None) while it can go on, or ("none", None)."""
        keys = tuple(keys)
        if keys in self.table:
            return "text", self.table[keys]
        return ("wait", None) if keys in self.prefixes else ("none", None)
