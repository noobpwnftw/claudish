"""The text box as retrieval (docs/design/architecture.md): read a range, or search, of the text box an
instruction was typed in, as it was when the instruction was sent. The model driver offers these as
tools when the text box is longer than the window it already sees; an agent gets them over MCP
(python -m claudish textbox-mcp)."""
import re

READ_LIMIT = 4000
SNIPPET = 160


class Textbox:
    def __init__(self, before="", after=""):
        self.text, self.caret = before + after, len(before)

    def read(self, start=0, length=2000):
        start = max(0, min(int(start), len(self.text)))
        end = min(len(self.text), start + max(0, min(int(length), READ_LIMIT)))
        caret = " (the caret is at %d)" % self.caret if start <= self.caret <= end else ""
        return "characters %d–%d of %d%s:\n%s" % (start, end, len(self.text), caret, self.text[start:end])

    def search(self, query, limit=5):
        """Lexical: the phrase where it occurs, else the places with most of its words."""
        query = str(query).strip()
        if not query:
            return "error: an empty query"
        # Matched in the text itself, ignoring case: offsets stay the text's own (lowercasing can
        # change a string's length, as Turkish İ does).
        spots = [m.start() for m in re.finditer(re.escape(query), self.text, re.IGNORECASE)]
        if not spots:
            words = set(re.findall(r"\w+", query.lower())) - {"the", "a", "an", "of", "to", "and", "in", "is"}
            scored = {}
            for word in words:
                for m in re.finditer(r"\b%s" % re.escape(word), self.text, re.IGNORECASE):
                    scored.setdefault(m.start() // SNIPPET, set()).add(word)
            spots = [block * SNIPPET for block, hits in sorted(scored.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
        if not spots:
            return "no match for %r in %d characters" % (query, len(self.text))
        found, last = [], -SNIPPET
        for spot in sorted(spots[:max(1, min(int(limit), 10))]):
            if spot - last < SNIPPET:
                continue  # overlaps the previous snippet
            start = max(0, spot - SNIPPET // 2)
            found.append("at %d: …%s…" % (spot, self.text[start:spot + SNIPPET].replace("\n", " ")))
            last = spot
        return "\n".join(found)

    def tools(self):
        """Local tools for claudish.tools.Toolbox.run."""
        return {
            "textbox__read": (
                "Read part of the text box the user is writing in (the context shows only the text "
                "around the caret). Offsets are characters.",
                {"type": "object", "properties": {"start": {"type": "integer"}, "length": {"type": "integer"}}},
                lambda arguments: self.read(arguments.get("start", 0), arguments.get("length", 2000))),
            "textbox__search": (
                "Find where words or a phrase occur in the text box the user is writing in; read around "
                "a result with textbox__read.",
                {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                lambda arguments: self.search(arguments.get("query", ""))),
        }
