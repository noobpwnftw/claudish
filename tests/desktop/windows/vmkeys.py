"""Type text into the Windows VM through QEMU's monitor (exact keys, unlike a VNC page).

python vmkeys.py 'Get-Date' [--enter]   (sends to the claudish-windows container)
"""
import subprocess
import sys

NAMES = {" ": "spc", "-": "minus", "=": "equal", "[": "bracket_left", "]": "bracket_right", "\\": "backslash",
         ";": "semicolon", "'": "apostrophe", "`": "grave_accent", ",": "comma", ".": "dot", "/": "slash"}
SHIFTED = {"_": "minus", "+": "equal", "{": "bracket_left", "}": "bracket_right", "|": "backslash",
           ":": "semicolon", '"': "apostrophe", "~": "grave_accent", "<": "comma", ">": "dot", "?": "slash",
           "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8", "(": "9", ")": "0"}


def key(char):
    if char.isalpha() and char.isascii():
        return ("shift-" if char.isupper() else "") + char.lower()
    if char.isdigit():
        return char
    if char in NAMES:
        return NAMES[char]
    if char in SHIFTED:
        return "shift-" + SHIFTED[char]
    raise ValueError("no key for %r" % char)


def main():
    text, enter = sys.argv[1], "--enter" in sys.argv[2:]
    commands = ["sendkey %s 20" % key(char) for char in text] + (["sendkey ret"] if enter else [])
    subprocess.run(["docker", "exec", "-i", "claudish-windows", "sh", "-c",
                    # QEMU works through queued keys after we send them; hang up only when it is done.
                    "nc -U -q %d /run/shm/monitor.sock >/dev/null" % (2 + len(commands) // 10)],
                   input="\n".join(commands) + "\n", text=True,
                   check=True)


if __name__ == "__main__":
    main()
