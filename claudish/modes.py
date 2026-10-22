"""Invocation modes: what the model does with the typed text. Every mode only offers a candidate."""
from . import model

CONTINUE_SYSTEM = (
    "Continue the user's unfinished text with the next few words, in the same language and voice, "
    "polished and slightly verbose. Output only the words that come next, not the text itself."
)
CONTINUE_EXAMPLES = [
    {"role": "user", "content": "Thanks for the quick review on"},
    {"role": "assistant", "content": "the parser change—much appreciated."},
]
INSTRUCT_SYSTEM = (
    "The user typed an instruction for text they want to write. Write that text, ready to send, "
    "in polished and slightly verbose English with a fondness for em dashes. Use the reference "
    "context for names, terms, and facts. Refer to people by name, or as they/them unless their "
    "pronouns are given. Output only the text itself, with no preamble or notes."
)
INSTRUCT_EXAMPLES = [
    {"role": "user", "content": "decline the meeting politely, propose thursday"},
    {"role": "assistant", "content": "Thank you for the invitation—unfortunately, I can't make that time. "
                                     "Would Thursday work instead?"},
]


def defaults(rewrite_prompt=None):
    """name -> {"system", "examples", "max_tokens", "candidates"}; max_tokens None means the backend's default.

    candidates: how many readings to offer. An instruction is sent on purpose and its result
    is awaited, so it offers a short list to pick from (1-3); while you type, one at a time."""
    system, examples = rewrite_prompt or (model.SYSTEM, model.EXAMPLES)
    return {
        "rewrite": {"system": system, "examples": examples, "max_tokens": None, "candidates": 1},
        "continue": {"system": CONTINUE_SYSTEM, "examples": CONTINUE_EXAMPLES, "max_tokens": 24, "candidates": 1},
        "instruct": {"system": INSTRUCT_SYSTEM, "examples": INSTRUCT_EXAMPLES, "max_tokens": 400, "candidates": 3},
    }


def finish(mode, text, output):
    """The candidate to offer for the model's output."""
    if mode != "continue":
        return output
    if output.startswith(text):  # Small models sometimes echo the prefix.
        output = output[len(text):]
    output = output.strip()
    if not output:
        return ""
    joiner = "" if text.endswith((" ", "\n")) or output[0] in ",.;:!?—)" else " "
    return text + joiner + output
