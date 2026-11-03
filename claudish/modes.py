"""Invocation modes: what the model does with the typed text. Every mode only offers a candidate.

The words for each mode are data, in claudish/templates.json; a profile's "templates" file has the
same shape and replaces only what it names (docs/configuration.md#templates)."""
import copy
import json
from pathlib import Path

TEMPLATES = json.loads(Path(__file__).with_name("templates.json").read_text(encoding="utf-8"))
MODE_KEYS = {"system", "job", "voice", "length", "plain", "frame", "examples", "parts", "max_tokens", "candidates", "note"}
SECTIONS = {"about", "modes", "tones", "box"}


def load(path):
    """A templates file, checked: the shipped shape, naming only what it changes."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    where = "templates %s" % path
    if not isinstance(data, dict) or set(data) - SECTIONS:
        raise ValueError("%s: takes only %s" % (where, ", ".join(sorted(SECTIONS))))
    for name, mode in (data.get("modes") or {}).items():
        check_mode(where, name, mode, name in TEMPLATES["modes"])
    for name, tone in ((data.get("tones") or {}).get("named") or {}).items():
        if not isinstance(tone, dict) or set(tone) - {"about", "persona", "modes"}:
            raise ValueError('%s: tone %r takes only "about", "persona" and "modes"' % (where, name))
        if not isinstance(tone.get("persona", ""), str):
            raise ValueError('%s: tone %r: "persona" is text' % (where, name))
        shipped = ((TEMPLATES["tones"]["named"].get(name) or {}).get("modes") or {})
        for mode_name, mode in (tone.get("modes") or {}).items():  # a shipped tone's mode may name only part
            check_mode("%s, tone %r," % (where, name), mode_name, mode, mode_name in shipped)
    return data


def check_mode(where, name, mode, known):
    """A mode's templates in a templates file (known: a shipped mode, which may name only part)."""
    if not isinstance(mode, dict) or set(mode) - MODE_KEYS:
        raise ValueError("%s: mode %r takes only %s" % (where, name, ", ".join(sorted(MODE_KEYS))))
    if not known and not (mode.get("system") or mode.get("voice")):
        raise ValueError('%s: mode %r needs a "system" (its whole wording) or a "voice"' % (where, name))
    for key in ("system", "job", "voice", "length"):
        if key in mode and not (isinstance(mode[key], str) and mode[key].strip()):
            raise ValueError("%s: mode %r needs a non-empty %s" % (where, name, key))
    if not all(isinstance(pair, list) and len(pair) == 2 and all(isinstance(s, str) for s in pair)
               for pair in mode.get("examples", [])):
        raise ValueError("%s: mode %r examples must be [input, answer] string pairs" % (where, name))
    if not all(isinstance(part, list) and len(part) == 4 and all(isinstance(s, str) for s in part)
               for part in mode.get("parts", [])):
        raise ValueError("%s: mode %r parts must be [before, part, after, replacement] strings" % (where, name))
    for key, low, high in (("max_tokens", 1, None), ("candidates", 1, 5)):
        value = mode.get(key)
        if value is not None and not (isinstance(value, int) and not isinstance(value, bool) and value >= low
                                      and (high is None or value <= high)):
            raise ValueError("%s: mode %r %s must be an integer%s" % (
                where, name, key, " from %d to %d" % (low, high) if high else ""))


def merged(override=None):
    """The shipped templates with a profile's over them, mode by mode and key by key (a named
    tone's too: changing its rewrite's voice keeps the rest of it)."""
    words = copy.deepcopy(TEMPLATES)
    for section in ("modes", "tones", "box"):
        over(words[section], (override or {}).get(section) or {})
    return words


def over(words, override):
    """override's keys over words', objects within objects merged; text and lists replaced. A mode's
    "voice" given takes the place of a "system" it would inherit (the whole wording, which wins)."""
    if "voice" in override and "system" not in override:
        words.pop("system", None)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(words.get(key), dict):
            over(words[key], value)
        else:
            words[key] = copy.deepcopy(value)


def messages(pairs, frame=None):
    """[input, answer] pairs as chat turns, the input in the mode's frame."""
    return [{"role": role, "content": frame.replace("{text}", text) if frame and role == "user" else text}
            for source, answer in pairs for role, text in (("user", source), ("assistant", answer))]


def defaults(override=None, tone=None):
    """name -> {"system", "plain", "examples", "parts", "max_tokens", "candidates", "custom", "box"[, "frame"]}.

    max_tokens None means the backend's default. candidates: how many readings to offer (an
    instruction is sent on purpose and awaited, so it offers a short list; while you type, one).
    tone: a tone other than the default: a named one (templates "tones": salesman, critic, bard, unhinged,
    proofread, ...), which brings its own wording and examples, or a few words of your own
    ("warm and friendly"), which fill the "tone" wording without examples (the default's teach
    its own tone). A mode's own system in the profile's templates wins over the tone, and is
    used as written in any box (custom)."""
    words = merged(override)
    own = (override or {}).get("modes") or {}
    specs = {}
    named = words["tones"]["named"]
    for name, mode in words["modes"].items():
        # A mode's wording is its job (what to do, and every guard), written once, with the tone's
        # voice and length filled in; a "system" is a whole wording of its own (a templates file's,
        # or a tone's that does a different job), used as written.
        examples, parts = mode.get("examples", []), mode.get("parts", [])
        custom = "system" in (own.get(name) or {})
        if custom:  # a wording of its own: only the examples and parts given with it, never the shipped ones
            examples, parts = own[name].get("examples", []), own[name].get("parts", [])
        voice, length, system = mode.get("voice"), mode.get("length"), mode.get("system")
        persona = None
        if tone and not custom and tone in named:
            wording = (named[tone].get("modes") or {}).get(name)
            if wording:
                examples, parts = wording.get("examples", []), wording.get("parts", [])
                system = wording.get("system")
                voice, length = wording.get("voice"), wording.get("length") or words["tones"]["length"]
                persona = named[tone].get("persona")  # a whole persona: the voice, before the job
        elif tone and not custom and name in words["tones"]["tone"]:
            voice, length, examples, parts = words["tones"]["tone"][name].replace("{tone}", tone), words["tones"]["length"], [], []
            system = None
        if not system:
            system = mode.get("job", "{voice}").replace("{voice}", voice or "").replace("{length}", length or words["tones"]["length"])
        if persona:
            system = persona + "\n\n---\n\n" + system
        specs[name] = {"system": system, "plain": mode.get("plain") or system,
                       "examples": messages(examples, mode.get("frame")), "max_tokens": mode.get("max_tokens"),
                       # A part of a text, rewritten in its place: [before, part, after, replacement].
                       "parts": messages([(words["box"]["in_place"].format(before=b, text=p, after=a), out)
                                          for b, p, a, out in parts]),
                       "candidates": mode.get("candidates") or 1, "custom": custom, "box": words["box"]}
        if mode.get("frame"):
            specs[name]["frame"] = mode["frame"]
    return specs


def finish(mode, text, output):
    """The candidate to offer for the model's output: continue's next words joined to your text."""
    if mode != "continue":
        return output
    # Small models sometimes echo the text before continuing it: only a whole echo, up to a word's
    # end ("I " then "in fact" is not one).
    import unicodedata

    def is_wide(c):  # Chinese and Japanese: no spaces between words (Korean has them; an emoji is a symbol)
        return unicodedata.east_asian_width(c) in "WFH" and not unicodedata.category(c).startswith("S") \
            and "HANGUL" not in unicodedata.name(c, "")

    def word_goes_on(at):  # "In" after "I", "We're" after "We"; never after a Chinese or Japanese character
        after = output[at:at + 2]
        return not is_wide(text[-1:] or " ") and (after[:1].isalnum() or after[:1] in "'’" and after[1:2].isalpha())
    echo = text.strip()
    if output.startswith(text) and not (text[-1:].isalnum() and word_goes_on(len(text))):
        output = output[len(text):]
    elif echo and output.lower().startswith(echo.lower()) and not word_goes_on(len(echo)):
        output = output[len(echo):]
    output = output.strip()
    # Or wrap all of it in quotes: a pair around the whole, not one that closes your open quote.
    if len(output) > 2 and output[0] == output[-1] == '"' and '"' not in output[1:-1] and text.count('"') % 2 == 0:
        output = output[1:-1].strip()
    if text.endswith((" ", "\n")):
        output = output.lstrip(",;: ")  # "hello " + ", how are you" reads "hello how are you"
    if not output:
        return ""
    # Chinese and Japanese take no spaces between words; Korean does, and an emoji (wide, but a
    # symbol) is spaced as a word.
    wide = any(is_wide(c) for c in (text[-1:] or " ", output[0]))
    # No space after an em dash, an opening bracket or a quote you opened, nor before a mark that
    # goes on your last letter.
    opened = text.endswith(("—", "(", "[", "“", "‘")) or text.endswith('"') and text.count('"') % 2 == 1
    joiner = "" if text.endswith((" ", "\n")) or output[0] in ",.;:!?—)" or wide or opened \
        or unicodedata.category(output[0]).startswith("M") else " "
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
