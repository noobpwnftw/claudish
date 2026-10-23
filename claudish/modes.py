"""Invocation modes: what the model does with the typed text. Every mode only offers a candidate."""
from . import model

CONTINUE_SYSTEM = (
    "Continue the user's unfinished text with the next few words, in the same language and voice, "
    "polished and slightly verbose. Output only the words that come next, not the text itself."
)
# The text arrives quoted, as a task, not as a message: chat-tuned models otherwise answer it
# ("hello" -> "Hello! How can I assist you today?") instead of continuing it as the writer.
CONTINUE_FRAME = 'Text so far: "{text}"\nThe next few words:'
CONTINUE_EXAMPLES = [
    # Not the demo's continue sample: a sample equal to an example gets the example's answer back,
    # which parroted() rightly drops, so the demo would show nothing.
    {"role": "user", "content": CONTINUE_FRAME.replace("{text}", "Sorry for the slow reply on")},
    {"role": "assistant", "content": "the budget—this week got away from me."},
    {"role": "user", "content": CONTINUE_FRAME.replace("{text}", "Hello everyone, ")},
    {"role": "assistant", "content": "I hope this finds you well—a quick update on the release."},
]
INSTRUCT_SYSTEM = (
    "The user typed an instruction for text they want to write. Write that text, ready to send, "
    "in polished and slightly verbose English with a fondness for em dashes. Use the reference "
    "context for names, terms, and facts. Refer to people by name, or as they/them unless their "
    "pronouns are given. Output only the text itself, with no preamble or notes."
)
# An instruction typed at a terminal prompt (G35): the screen comes with it, and the answer goes
# where commands are typed. The prose template's voice and examples do not apply there.
TERMINAL_SYSTEM = (
    "The user typed an instruction at a terminal prompt; the terminal screen shows what happened "
    "before it. Reply with the command line that does what they want, ready to run, and nothing "
    "else: no explanation, no quotes, no code fence."
)
INSTRUCT_EXAMPLES = [
    {"role": "user", "content": "decline the meeting politely, propose thursday"},
    {"role": "assistant", "content": "Thank you for the invitation—unfortunately, I can't make that time. "
                                     "Would Thursday work instead?"},
]


def toned(tone):
    """The templates in another voice (a profile's "tone", such as "plain and concise"), for
    rewrite, continue, and instruct. Claudish's voice (polished, slightly verbose, em dashes) is
    the default and the identity; the examples teach that voice, so a tone goes without them."""
    return {
        "rewrite": ("Rewrite the user's text in %s English. Keep its meaning, names, numbers and language. "
                    "Output only the rewritten text, no explanation." % tone, []),
        "continue": ("Continue the user's unfinished text with the next few words, in the same language, "
                     "%s. Output only the words that come next, not the text itself." % tone, []),
        "instruct": ("The user typed an instruction for text they want to write. Write that text, ready to "
                     "send, in %s English. Use the reference context for names, terms, and facts. Refer to "
                     "people by name, or as they/them unless their pronouns are given. Output only the text "
                     "itself, with no preamble or notes." % tone, []),
    }


def defaults(rewrite_prompt=None, tone=None):
    """name -> {"system", "examples", "max_tokens", "candidates"}; max_tokens None means the backend's default.

    candidates: how many readings to offer. An instruction is sent on purpose and its result
    is awaited, so it offers a short list to pick from (1-3); while you type, one at a time.
    tone: a voice other than Claudish's (see toned); a rewrite template from --prompt wins."""
    system, examples = rewrite_prompt or (model.SYSTEM, model.EXAMPLES)
    voices = toned(tone) if tone else {}
    if tone and rewrite_prompt is None:
        system, examples = voices["rewrite"]
    continued, continue_examples = voices.get("continue") or (CONTINUE_SYSTEM, CONTINUE_EXAMPLES)
    instructed, instruct_examples = voices.get("instruct") or (INSTRUCT_SYSTEM, INSTRUCT_EXAMPLES)
    return {
        "rewrite": {"system": system, "examples": examples, "max_tokens": None, "candidates": 1},
        "continue": {"system": continued, "examples": continue_examples, "max_tokens": 24, "candidates": 1,
                     "frame": CONTINUE_FRAME},
        "instruct": {"system": instructed, "examples": instruct_examples, "max_tokens": 400, "candidates": 3},
    }


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
    """A continuation that is not new: one of the template's own example answers, or words
    already in the text before the caret. Offering those is noise from any model."""
    if mode != "continue" or not candidate.startswith(text):
        return False
    rest = candidate[len(text):].strip().lower()
    if not rest:
        return True
    answers = {m["content"].strip().lower() for m in examples if m.get("role") == "assistant"}
    return rest in answers or (len(rest) >= 12 and rest in text.lower())
