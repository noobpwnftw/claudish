"""Fix the last failed shell command with the configured model; never runs anything itself.

eval "$(claudish shell-hook bash)"   # or zsh, in your shell's rc file
gti status                           # fails
fix                                  # suggests "git status" for you to accept or edit
"""
import os
import shlex
import shutil
from pathlib import Path

SYSTEM = (
    "You fix a failed shell command. Reply with only the corrected command on one line: "
    "no explanation, no quotes, no code fence. Keep the user's intent, arguments, paths, and names. "
    "If you cannot tell what is wrong, reply with the original command unchanged."
)
EXAMPLES = [
    ("Command: gti status\nExit status: 127\nNot found: gti\nSimilar programs: git, gtk-launch",
     "git status"),
    ("Command: apt install ripgrep\nExit status: 100", "sudo apt install ripgrep"),
    ("Command: git comit -m 'Fix typo'\nExit status: 1", "git commit -m 'Fix typo'"),
    ("Command: ls -l ~/Downloads\nExit status: 2", "ls -l ~/Downloads"),
]


def state_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
    return Path(base) / ("claudish-%s-last-failure" % os.getuid() if hasattr(os, "getuid") else "claudish-last-failure")


HOOKS = {
    # Must run first in PROMPT_COMMAND to see $?. Records failures only, never Ctrl+C (130).
    "bash": r'''__claudish_record() {
  local status=$? command
  command=$(HISTTIMEFORMAT= builtin history 1 | sed 's/^ *[0-9]* *//')
  if [ "$status" -ne 0 ] && [ "$status" -ne 130 ] && [ "${command%% *}" != fix ]; then
    (umask 077; printf '%s\n%s\n%s' "$status" "$PWD" "$command" > "__STATE__")
  fi
  return $status
}
PROMPT_COMMAND="__claudish_record${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fix() {
  local suggestion
  suggestion=$(__CLAUDISH__ fix "$@") || return
  if [ "${BASH_VERSINFO[0]}" -ge 4 ]; then
    read -e -i "$suggestion" -p "fix> " suggestion && history -s -- "$suggestion" && eval -- "$suggestion"
  else  # bash 3 (macOS) has no read -i: offer it through history; Up arrow recalls it.
    history -s -- "$suggestion" && printf 'fix> %s  (press Up to edit, Enter to run)\n' "$suggestion"
  fi
}''',
    "zsh": r'''__claudish_preexec() { __claudish_command=$1 }
__claudish_precmd() {
  local exit_status=$?
  if [[ -n $__claudish_command && $exit_status -ne 0 && $exit_status -ne 130 && ${__claudish_command%% *} != fix ]]; then
    (umask 077; print -r -- "$exit_status"$'\n'"$PWD"$'\n'"$__claudish_command" > "__STATE__")
  fi
  __claudish_command=
}
autoload -Uz add-zsh-hook
add-zsh-hook preexec __claudish_preexec
add-zsh-hook precmd __claudish_precmd
fix() {
  local suggestion
  suggestion=$(__CLAUDISH__ fix "$@") || return
  print -z -- "$suggestion"
}''',
}


def shell_hook(shell, launcher="claudish"):
    return HOOKS[shell].replace("__STATE__", str(state_path())).replace("__CLAUDISH__", launcher)


def last_failure(path=None):
    """(exit status, directory, command) recorded by the shell hook, or None."""
    try:
        status, directory, command = Path(path or state_path()).read_text(encoding="utf-8").split("\n", 2)
        return int(status), directory, command.strip()
    except (OSError, ValueError):
        return None


def executables():
    names = set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        try:
            names.update(entry.name for entry in os.scandir(directory) if entry.is_file())
        except OSError:
            pass
    return names


def typo_distance(a, b, limit=2):
    """Edit distance counting a swap of adjacent letters as one edit (optimal string alignment)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2, previous = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        current = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                current[j] = min(current[j], previous2[j - 2] + 1)
        previous2, previous = previous, current
    return previous[-1]


def similar_programs(name, names=None):
    limit = 1 if len(name) < 5 else 2
    scored = sorted((typo_distance(name, other, limit), other) for other in (names or executables()))
    return [other for distance, other in scored if distance <= limit][:3]


def describe(command, status, names=None, found=None):
    """The model's input: the command plus cheap, local facts. Nothing is executed.

    The working directory is left out: small models paste it into the command.
    `names` and `found` replace PATH lookups, for reproducible evaluation."""
    lines = ["Command: " + command, "Exit status: %d" % status]
    try:
        program = shlex.split(command)[0] if command.strip() else ""
    except ValueError:
        program = command.split()[0] if command.split() else ""
    missing = (not found) if found is not None else not shutil.which(program)
    if program and "/" not in program and "=" not in program and missing:
        lines.append("Not found: " + program)
        similar = similar_programs(program, names)
        if similar:
            lines.append("Similar programs: " + ", ".join(similar))
    return "\n".join(lines)


def clean(output, original):
    """First line of the reply, without fences, prompts, or quotes; None when there is no fix."""
    lines = [line.strip() for line in output.strip().splitlines() if line.strip() and not line.strip().startswith("```")]
    if not lines:
        return None
    line = lines[0]
    if line.startswith("$ "):
        line = line[2:]
    if len(line) > 1 and line[0] == line[-1] == "`":
        line = line[1:-1]
    return None if same_command(line, original) else line


def same_command(a, b):
    """True when two command lines parse to the same words (quoting differences only)."""
    try:
        return shlex.split(a) == shlex.split(b)
    except ValueError:
        return a.strip() == b.strip()


def suggest(rewriter, command, status, names=None, found=None):
    """A suggested fix, or None when the model offers no change."""
    return clean(rewriter.rewrite(describe(command, status, names, found))["text"], command)


def examples():
    return [message for source, target in EXAMPLES for message in (
        {"role": "user", "content": source}, {"role": "assistant", "content": target})]
