"""Invocation modes: what the model does with the typed text. Every mode only offers a candidate.

The words for each mode are data, in claudish/templates.json; a profile's "templates" file has the
same shape and replaces only what it names (docs/configuration.md#templates)."""
import copy
import json
from pathlib import Path

TEMPLATES = json.loads(Path(__file__).with_name("templates.json").read_text(encoding="utf-8"))
MODE_KEYS = {"system", "plain", "frame", "examples", "max_tokens", "candidates", "note"}
SECTIONS = {"about", "modes", "tones", "box"}


def load(path):
    """A templates file, checked: the shipped shape, naming only what it changes."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    where = "templates %s" % path
    if not isinstance(data, dict) or set(data) - SECTIONS:
        raise ValueError("%s: takes only %s" % (where, ", ".join(sorted(SECTIONS))))
    for name, mode in (data.get("modes") or {}).items():
        check_mode(where, name, mode, name in TEMPLATES["modes"])
    for name, tone in ((data.get("tones") or {}).get("named") or {}).items():
        if not isinstance(tone, dict) or set(tone) - {"about", "modes"}:
            raise ValueError('%s: tone %r takes only "about" and "modes"' % (where, name))
        for mode_name, mode in (tone.get("modes") or {}).items():
            check_mode("%s, tone %r," % (where, name), mode_name, mode, False)
    return data


def check_mode(where, name, mode, known):
    """A mode's templates in a templates file (known: a shipped mode, which may name only part)."""
    if not isinstance(mode, dict) or set(mode) - MODE_KEYS:
        raise ValueError("%s: mode %r takes only %s" % (where, name, ", ".join(sorted(MODE_KEYS))))
    if not known and not mode.get("system"):
        raise ValueError('%s: mode %r needs a "system"' % (where, name))
    if "system" in mode and not (isinstance(mode["system"], str) and mode["system"].strip()):
        raise ValueError("%s: mode %r needs a non-empty system" % (where, name))
    if not all(isinstance(pair, list) and len(pair) == 2 and all(isinstance(s, str) for s in pair)
               for pair in mode.get("examples", [])):
        raise ValueError("%s: mode %r examples must be [input, answer] string pairs" % (where, name))
    for key, low, high in (("max_tokens", 1, None), ("candidates", 1, 5)):
        value = mode.get(key)
        if value is not None and not (isinstance(value, int) and not isinstance(value, bool) and value >= low
                                      and (high is None or value <= high)):
            raise ValueError("%s: mode %r %s must be an integer%s" % (
                where, name, key, " from %d to %d" % (low, high) if high else ""))


def merged(override=None):
    """The shipped templates with a profile's over them, mode by mode and key by key."""
    words = copy.deepcopy(TEMPLATES)
    for section in ("modes", "tones", "box"):
        for key, value in ((override or {}).get(section) or {}).items():
            if isinstance(value, dict) and isinstance(words[section].get(key), dict):
                words[section][key] = dict(words[section][key], **value)
            else:
                words[section][key] = value
    return words


def messages(pairs, frame=None):
    """[input, answer] pairs as chat turns, the input in the mode's frame."""
    return [{"role": role, "content": frame.replace("{text}", text) if frame and role == "user" else text}
            for source, answer in pairs for role, text in (("user", source), ("assistant", answer))]


def defaults(override=None, tone=None):
    """name -> {"system", "plain", "examples", "max_tokens", "candidates", "custom", "box"[, "frame"]}.

    max_tokens None means the backend's default. candidates: how many readings to offer (an
    instruction is sent on purpose and awaited, so it offers a short list; while you type, one).
    tone: a voice other than the default: a named one (templates "tones": salesman, critic, bard,
    proofread, ...), which brings its own wording and examples, or a few words of your own
    ("warm and friendly"), which fill the "voice" wording without examples (the default's teach
    its own voice). A mode's own system in the profile's templates wins over the tone, and is
    used as written in any box (custom)."""
    words = merged(override)
    own = (override or {}).get("modes") or {}
    specs = {}
    for name, mode in words["modes"].items():
        system, examples = mode["system"], mode.get("examples", [])
        custom = "system" in (own.get(name) or {})
        named = words["tones"]["named"]
        if tone and not custom and tone in named:
            voice = (named[tone].get("modes") or {}).get(name)
            if voice:
                system, examples = voice["system"], voice.get("examples", [])
        elif tone and not custom and name in words["tones"]["voice"]:
            system, examples = words["tones"]["voice"][name].replace("{tone}", tone), []
        specs[name] = {"system": system, "plain": mode.get("plain") or system,
                       "examples": messages(examples, mode.get("frame")), "max_tokens": mode.get("max_tokens"),
                       "candidates": mode.get("candidates") or 1, "custom": custom, "box": words["box"]}
        if mode.get("frame"):
            specs[name]["frame"] = mode["frame"]
    return specs


def finish(mode, text, output):
    """The candidate to offer for the model's output."""
    if mode != "continue":
        return output
    # Small models sometimes echo the text, or its last words, before continuing it.
    if output.startswith(text):
        output = output[len(text):]
    elif text.strip() and output.lower().startswith(text.strip().lower()):
        output = output[len(text.strip()):]
    output = output.strip().strip('"').strip()
    if text.endswith((" ", "\n")):
        output = output.lstrip(",;: ")  # "hello " + ", how are you" reads "hello how are you"
    if not output:
        return ""
    joiner = "" if text.endswith((" ", "\n")) or output[0] in ",.;:!?—)" else " "
    return text + joiner + output


def parroted(mode, text, candidate, examples=()):
    """An answer that is not about what you typed: one of the template's own example answers
    (a small model given nonsense, "tttt", repeats its example), or, in continue, words already
    in the text before the caret. Offering those is noise from any model."""
    answers = {m["content"].strip().lower() for m in examples if m.get("role") == "assistant"}
    if mode != "continue":
        asked = {m["content"].strip().lower() for m in examples if m.get("role") == "user"}
        return candidate.strip().lower() in answers and text.strip().lower() not in asked
    if not candidate.startswith(text):
        return False
    rest = candidate[len(text):].strip().lower()
    if not rest:
        return True
    return rest in answers or (len(rest) >= 12 and rest in text.lower())
