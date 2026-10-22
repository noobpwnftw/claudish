"""A tiny stdio MCP server for the context tests (needs the optional MCP SDK)."""
import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("claudish-test")


@server.tool()
def pull_request_diff(number: int) -> str:
    """Return a fake diff for a pull request."""
    return "PR #%d: + retry the flaky upload (token %s)" % (number, os.environ.get("TEST_TOKEN", "unset"))


@server.tool(annotations={"readOnlyHint": True})
def ci_status(branch: str) -> str:
    """CI status of a branch (read-only)."""
    return "CI for %s: 41 passed, 1 failed (test_upload_retry, timeout after 30 s)" % branch


@server.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def delete_branch(branch: str) -> str:
    """Delete a branch (side effect: never offered without approval)."""
    raise AssertionError("delete_branch must never be called by the read-only tool loop")


@server.tool()
def broken() -> str:
    """Always fails."""
    raise ValueError("nope")


@server.resource("notes://style")
def style() -> str:
    """House style notes."""
    return "Prefer em dashes."


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["http"]:  # An app exposing MCP on a local socket.
        server.run("streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run("stdio")
