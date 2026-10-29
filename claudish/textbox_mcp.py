"""claudish textbox-mcp: the text box an instruction was typed in, as an MCP server for the
conversation's agent (docs/design/architecture.md, "For agents"). Claudish starts it for the agent with
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
    from .modes import TEMPLATES
    words = TEMPLATES["box"]["textbox"]  # what the agent reads about this server (templates.json)
    server = MCPServer("textbox", instructions=words["instructions"])

    @server.tool(description=words["read"], annotations={"readOnlyHint": True})
    def read(start: int = 0, length: int = 2000) -> str:
        return ask({"op": "read", "start": start, "length": length})

    @server.tool(description=words["search"], annotations={"readOnlyHint": True})
    def search(query: str) -> str:
        return ask({"op": "search", "query": query})

    server.run()


if __name__ == "__main__":
    main()
