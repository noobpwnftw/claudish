"""claudish textbox-mcp: the text box an instruction was typed in, as an MCP server for the
conversation's agent (docs/design/instruct.md, "For agents"). Claudish starts it for the agent with
--mcp-config; it reads through the service with the conversation's token, so it sees the text box
as of the latest instruction. Needs the MCP SDK: pip install "claudish-ime[mcp]"."""
import json
import os
from urllib.request import ProxyHandler, Request, build_opener

OPENER = build_opener(ProxyHandler({}))


def ask(body):
    url = "%s/conversations/%s/textbox" % (os.environ["CLAUDISH_URL"], os.environ["CLAUDISH_CONVERSATION"])
    request = Request(url, json.dumps(body).encode(), {"Content-Type": "application/json",
                                                       "X-Claudish-Token": os.environ["CLAUDISH_TOKEN"]})
    with OPENER.open(request, timeout=10) as response:
        return json.load(response)["text"]


def main():
    from mcp.server.mcpserver import MCPServer
    server = MCPServer("textbox", instructions="The text box the user is typing in, where your answer will be "
                                               "inserted at the caret. Read or search it when the "
                                               "instruction refers to its content.")

    @server.tool(annotations={"readOnlyHint": True})
    def read(start: int = 0, length: int = 2000) -> str:
        """Read part of the text box the user is writing in. Offsets are characters; the result
        says where the caret is."""
        return ask({"op": "read", "start": start, "length": length})

    @server.tool(annotations={"readOnlyHint": True})
    def search(query: str) -> str:
        """Find where words or a phrase occur in the text box; read around a result with read."""
        return ask({"op": "search", "query": query})

    server.run()


if __name__ == "__main__":
    main()
