"""A stdio MCP server whose one tool takes its time (a server that hangs): tests/test_tool_stop.py."""
import time

from mcp.server.mcpserver import MCPServer

server = MCPServer("claudish-slow")


@server.tool(annotations={"readOnlyHint": True})
def wait(seconds: float) -> str:
    """Take its time."""
    time.sleep(seconds)
    return "waited"


if __name__ == "__main__":
    server.run("stdio")
