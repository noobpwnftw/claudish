"""A tiny stdio MCP server for the context tests (needs the optional MCP SDK)."""
import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("claudish-test")


@server.tool()
def pull_request_diff(number: int) -> str:
    """Return a fake diff for a pull request."""
    return "PR #%d: + retry the flaky upload (token %s)" % (number, os.environ.get("TEST_TOKEN", "unset"))


@server.tool()
def broken() -> str:
    """Always fails."""
    raise ValueError("nope")


@server.resource("notes://style")
def style() -> str:
    """House style notes."""
    return "Prefer em dashes."


if __name__ == "__main__":
    server.run("stdio")
