"""What a model's plain-text answer is read through when its backend takes no schema (a command,
a server without json_schema; claudish/shapes.py is the rule): known habits of models, declared
here and nowhere else. Each one strips what is not the answer; none rewrites the answer."""
import re

# A tool call the server did not parse, left in the reply as text (Gemma's "<|tool_call>call:...",
# Qwen's "<tool_call>"): never a draft.
TOOL_MARKUP = ("<|tool_call>", "<tool_call>", "<|tool_call|>")

# Wrapping a model can put around its answer: reasoning, a fence, quotes, a line introducing it.
THINKING = re.compile(r"^\s*<think(?:ing)?\b[^>]*>.*?(</think(?:ing)?>|$)\s*", re.S | re.I)
FENCE = re.compile(r"^\s*```[\w-]*\n(.*?)\n```\s*$", re.S)
INTRO = re.compile(r"^(here(?: is|'s| are)|sure[,!.]|certainly[,!.])[^\n]*:\s*\n+", re.I)
QUOTES = ('""', "“”", "''", "‘’")


def tidy(text, output, terminal=False):
    """A plain answer without what a model wraps it in: a <think> block, a fence around all of it, a
    first line introducing it ("Here's a rewrite:"), one pair of quotes around all of it (unless
    your text was quoted)."""
    output = THINKING.sub("", output, count=1)
    fenced = FENCE.match(output)
    if fenced and "```" not in fenced.group(1) and not text.strip().startswith("```"):  # one block, not your own
        output = fenced.group(1)
    output = output.strip()
    intro = INTRO.match(output)
    if intro and intro.group(0).strip().lower() not in text.lower() and not same_start(text, intro.group(0)):
        output = output[intro.end():].strip()  # your own first line ("Here are the notes:"), rewritten too, stays
    output = unmarked(text, output)
    for pair in () if terminal else QUOTES:  # a quoted path is how cmd runs a program with spaces in it
        if (len(output) > 2 and output[0] == pair[0] and output[-1] == pair[1] and pair[0] not in output[1:-1]
                and not text.strip().startswith(pair[0])):
            output = output[1:-1].strip()
            break
    return output


def same_start(text, line):
    """Whether your text starts with the line's first word (a rewrite of your own first line)."""
    first = lambda words: (re.findall(r"[\w']+", words.lower()) or [""])[0]
    return first(text) == first(line)


def unmarked(text, output):
    """The part rewritten in place, as it was marked ([[...]], one span), without its marks."""
    if output.startswith("[[") and output.endswith("]]") and "[[" not in text \
            and "[[" not in output[2:-2] and "]]" not in output[2:-2]:
        return output[2:-2].strip()
    return output


def plain(text, output, terminal=False):
    """A plain-text answer, read: None when it is a tool call the server left unparsed."""
    if any(markup in output for markup in TOOL_MARKUP):
        return None
    return tidy(text, output, terminal)
