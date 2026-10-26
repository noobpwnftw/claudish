"""What a model's plain-text answer is read through when its backend takes no schema (a command,
a server without json_schema; claudish/shapes.py is the rule): known habits of models, declared
here and nowhere else. Each one strips what is not the answer; none rewrites the answer."""
import re

# A tool call the server did not parse, left in the reply as text (Gemma's "<|tool_call>call:...",
# Qwen's "<tool_call>"): never a draft.
TOOL_MARKUP = ("<|tool_call>", "<tool_call>", "<|tool_call|>")

# Wrapping a model can put around its answer: reasoning, a fence, quotes, a line introducing it.
THINKING = re.compile(r"^\s*<think\b[^>]*>.*?(</think>|$)\s*", re.S | re.I)
FENCE = re.compile(r"^\s*```[\w-]*\n(.*?)\n```\s*$", re.S)
INTRO = re.compile(r"^(here(?: is|'s| are)|sure[,!.]|certainly[,!.])[^\n]*:\s*\n+", re.I)
QUOTES = ('""', "“”", "''", "‘’")


def tidy(text, output):
    """A plain answer without what a model wraps it in: a <think> block, a fence around all of it, a
    first line introducing it ("Here's a rewrite:"), one pair of quotes around all of it (unless
    your text was quoted)."""
    output = THINKING.sub("", output, count=1)
    fenced = FENCE.match(output)
    if fenced:
        output = fenced.group(1)
    output = INTRO.sub("", output.strip(), count=1).strip()
    if output.startswith("[[") and output.endswith("]]") and "[[" not in text:  # the part, as it was marked
        output = output[2:-2].strip()
    for pair in QUOTES:
        if (len(output) > 2 and output[0] == pair[0] and output[-1] == pair[1] and pair[0] not in output[1:-1]
                and not text.strip().startswith(pair[0])):
            output = output[1:-1].strip()
            break
    return output


def plain(text, output):
    """A plain-text answer, read: None when it is a tool call the server left unparsed."""
    if any(markup in output for markup in TOOL_MARKUP):
        return None
    return tidy(text, output)
