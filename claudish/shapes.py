"""The shape of what a model answers (docs/design/architecture.md, G69): every mode answers
{"drafts": [text, ...]}, one draft, or two or three versions when an instruction asks for several.
A backend that takes a schema is held to it (an OpenAI-compatible server's response_format, the
Claude API's output_config, Claude Code's --json-schema, a Codex turn's outputSchema), so the
answer is read as data and never cleaned. On an OpenAI-compatible server an instruction's tool
calls are steps of the same schema, {"call": tool, "arguments": {...}}, each tool with its own
argument schema: the server enforces them, where a model's native tool-call format may not be. A
backend without a schema answers in plain text, read through claudish.quirks."""
import json

ANSWER = {"type": "object", "properties": {"drafts": {"type": "array", "items": {"type": "string"},
                                                     "minItems": 1, "maxItems": 3}},
          "required": ["drafts"], "additionalProperties": False}
OBJECT = {"type": "object"}  # a tool's arguments when its own schema cannot be used


def answer_format():
    """response_format for an answer: OpenAI-compatible servers (llama.cpp compiles it to a grammar)."""
    return {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": ANSWER}}


def step_format(offered, loose=False):
    """response_format for one step of the tool loop: a call to one of the offered tools (OpenAI
    tool definitions), with its own arguments (loose: any object), or the answer."""
    calls = []
    for tool in offered:
        function = tool["function"]
        arguments = function.get("parameters") or {"type": "object", "properties": {}}
        calls.append({"type": "object", "properties": {"call": {"const": function["name"]},
                                                       "arguments": arguments if usable(arguments) and not loose
                                                       else OBJECT},
                      "required": ["call", "arguments"], "additionalProperties": False})
    # Not strict: a tool's own schema may not meet a hosted API's strict rules (every property
    # required); a grammar (llama.cpp) holds it either way.
    return {"type": "json_schema", "json_schema": {"name": "step", "strict": False,
                                                  "schema": {"anyOf": calls + [ANSWER]}}}


def usable(schema):
    """A tool's argument schema a grammar can hold: an object, without references to elsewhere."""
    return isinstance(schema, dict) and schema.get("type") == "object" and "$ref" not in json.dumps(schema)


def example(answer):
    """An example's answer, in the shape the model answers."""
    return answered([answer])


def answered(drafts):
    """An answer of these drafts, as the model gave it."""
    return json.dumps({"drafts": list(drafts)}, ensure_ascii=False)


def as_answered(messages):
    """Examples and earlier turns with their answers in the shape the model answers, so it answers
    in kind: a plain assistant text becomes {"drafts": [text]}; tool calls stay as they are."""
    return [dict(m, content=example(m.get("content") or ""))
            if m.get("role") == "assistant" and not m.get("tool_calls") and drafts(m.get("content")) is None else m
            for m in messages]


def with_tools(messages, offered, words):
    """The system prompt with the offered tools and what each does, as a schema's names alone do
    not say (words: templates.json box.steps)."""
    listed = "\n".join("- %s: %s" % (tool["function"]["name"], (tool["function"].get("description") or "").strip())
                        for tool in offered)
    return [dict(m, content=m["content"] + "\n\n" + words + "\n" + listed) if i == 0 and m.get("role") == "system" else m
            for i, m in enumerate(messages)]


def as_steps(messages):
    """The tool loop's history (OpenAI tool_calls and tool results) as the steps the model wrote and
    the results it was given: the shape it answers in, rather than a native format it does not."""
    out, names = [], {}
    for message in messages:
        calls = message.get("tool_calls") if message.get("role") == "assistant" else None
        if calls:
            for call in calls:
                function = call.get("function") or {}
                names[call.get("id")] = function.get("name")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except ValueError:
                    arguments = {}
                out.append({"role": "assistant", "content": json.dumps({"call": function.get("name"),
                                                                        "arguments": arguments}, ensure_ascii=False)})
        elif message.get("role") == "tool":
            out.append({"role": "user", "content": "Result of %s:\n%s" % (names.get(message.get("tool_call_id"), "the call"),
                                                                         message.get("content") or "")})
        else:
            out.append(message)
    return out


def as_message(content, index=0):
    """A step the model wrote, as the tool loop's OpenAI message: a call becomes tool_calls; the
    answer stays the content, read by drafts()."""
    try:
        step = json.loads(content or "")
    except ValueError:
        return {"role": "assistant", "content": content or ""}
    if isinstance(step, dict) and isinstance(step.get("call"), str):
        arguments = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
        return {"role": "assistant", "content": "", "tool_calls": [{
            "id": "step-%d" % index, "type": "function",
            "function": {"name": step["call"], "arguments": json.dumps(arguments, ensure_ascii=False)}}]}
    return {"role": "assistant", "content": content}


def drafts(content):
    """The drafts in an answer, or None when it is not one (a backend without a schema)."""
    if isinstance(content, dict):
        found = content.get("drafts")
    else:
        try:
            found = json.loads(content or "").get("drafts")
        except (ValueError, AttributeError):
            return None
    if not isinstance(found, list):
        return None
    return [text.strip() for text in found if isinstance(text, str) and text.strip()] or None
