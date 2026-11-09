import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from claudish import config, mcp_setup

SECRET = "sk-very-secret-123"
SERVER = str(Path(__file__).with_name("mcp_server.py"))


class MCPSetupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        env = {"XDG_CONFIG_HOME": str(self.home / ".config"), "HOME": str(self.home)}
        patches = [patch.dict(os.environ, env), patch.object(Path, "home", return_value=self.home),
                   patch("claudish.mcp_setup.platform.system", return_value="Linux"),
                   patch.object(Path, "cwd", return_value=self.home)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        desktop = self.home / ".config/Claude/claude_desktop_config.json"
        desktop.parent.mkdir(parents=True)
        desktop.write_text(json.dumps({"mcpServers": {
            "github": {"command": "github-mcp-server", "args": ["stdio"], "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": SECRET}},
            "docs": {"type": "http", "url": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer " + SECRET}},
            "notes": {"command": sys.executable, "args": [SERVER], "env": {"TEST_TOKEN": "${MY_TOKEN}"}},
        }}))
        (self.home / ".claude.json").write_text(json.dumps({"mcpServers": {
            "remote": {"type": "sse", "url": "https://sse.example.com/sse", "headers": {"X-Key": "${REMOTE_KEY}"}}}}))

    def test_a_projects_mcp_json_is_not_imported(self):
        # A cloned repo's .mcp.json can name any command; it stays with its project.
        (self.home / ".mcp.json").write_text(json.dumps({"mcpServers": {
            "project": {"command": "sh", "args": ["-c", "anything"]}}}))
        self.assertNotIn("project", mcp_setup.discover())
        self.assertEqual(set(mcp_setup.discover()), {"github", "docs", "notes", "remote"})

    def test_what_claude_mcp_add_keeps_per_project_is_found_and_what_is_off_is_not(self):
        """`claude mcp add` (local scope, its default) keeps a server under projects[path]; Cline-style
        configs mark one "disabled"; Claude Code turns one off per project."""
        (self.home / ".claude.json").write_text(json.dumps({
            "mcpServers": {"remote": {"type": "sse", "url": "https://sse.example.com/sse"}},
            "projects": {"/home/me/app": {
                "mcpServers": {"linear-server": {"type": "http", "url": "https://mcp.linear.app/mcp"},
                               "sqlite": {"command": "uvx", "args": ["mcp-server-sqlite"]},
                               "github": {"command": "docker", "args": ["run", "-i", "ghcr.io/github/github-mcp-server"]}},
                "disabledMcpServers": ["sqlite"]}}}))
        desktop = self.home / ".config/Claude/claude_desktop_config.json"
        data = json.loads(desktop.read_text())
        data["mcpServers"]["old"] = {"command": "old-server", "disabled": True}
        data["mcpServers"]["socket"] = {"type": "ws", "url": "ws://localhost:9000"}
        desktop.write_text(json.dumps(data))
        skipped = []
        found = mcp_setup.discover(skipped)
        self.assertIn("linear-server", found)
        self.assertIn("project /home/me/app", found["linear-server"][0])
        self.assertNotIn("sqlite", found)
        self.assertNotIn("old", found)
        self.assertEqual(found["github"][0], "Claude Desktop")  # found first; the project's is said
        self.assertEqual({name for name, _, _ in skipped}, {"sqlite", "old", "github"})
        _, out = self.run_quiet(mcp_setup.import_servers)
        servers = json.loads(config.default_path().read_text())["mcp_servers"]
        self.assertNotIn("socket", servers)
        self.assertIn("WebSocket", out)
        self.assertIn("linear-server: no token header", out)
        config.resolve()

    def run_quiet(self, function, *args, **kwargs):
        out = io.StringIO()
        with redirect_stdout(out):
            status = function(*args, **kwargs)
        return status, out.getvalue()

    def test_import_copies_servers_but_never_secrets(self):
        status, out = self.run_quiet(mcp_setup.import_servers)
        self.assertEqual(status, 0)
        written = config.default_path().read_text()
        self.assertNotIn(SECRET, written)
        servers = json.loads(written)["mcp_servers"]
        self.assertEqual(servers["github"], {"command": "github-mcp-server", "args": ["stdio"],
                                             "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "$GITHUB_PERSONAL_ACCESS_TOKEN"}})
        self.assertEqual(servers["docs"]["headers"], {"Authorization": "$CLAUDISH_MCP_DOCS_AUTHORIZATION"})
        self.assertEqual(servers["notes"]["env"], {"TEST_TOKEN": "${MY_TOKEN}"})  # a reference, as written
        self.assertEqual(servers["remote"], {"url": "https://sse.example.com/sse", "type": "sse",
                                             "headers": {"X-Key": "${REMOTE_KEY}"}})
        self.assertEqual(servers["docs"]["type"], "http")  # Claude Code skips a url without its type
        self.assertIn("GITHUB_PERSONAL_ACCESS_TOKEN", out)
        self.assertNotIn(SECRET, out)
        config.resolve()  # the result is a valid config

    def test_dry_run_writes_nothing_and_existing_servers_are_kept(self):
        self.run_quiet(mcp_setup.import_servers, dry_run=True)
        self.assertFalse(config.default_path().exists())
        self.run_quiet(mcp_setup.import_servers)
        data = json.loads(config.default_path().read_text())
        data["mcp_servers"]["github"]["args"] = ["mine"]
        config.default_path().write_text(json.dumps(data))
        _, out = self.run_quiet(mcp_setup.import_servers)
        self.assertIn("skip github", out)
        self.assertEqual(json.loads(config.default_path().read_text())["mcp_servers"]["github"]["args"], ["mine"])

    def test_list_and_context_test_with_a_real_server(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')
        self.run_quiet(mcp_setup.import_servers)
        data = json.loads(config.default_path().read_text())
        data["mcp_servers"] = {"notes": data["mcp_servers"]["notes"]}  # only the server that exists here
        data["profiles"][data["profile"]]["bindings"] = [{"app": "code", "context": [  # the default profile
            {"type": "mcp", "server": "notes", "tool": "pull_request_diff", "arguments": {"number": 3}, "timeout": 20}]}]
        config.default_path().write_text(json.dumps(data))
        with patch.dict(os.environ, {"MY_TOKEN": "t-1"}):
            status, out = self.run_quiet(mcp_setup.list_servers)
            self.assertEqual(status, 0, out)
            self.assertIn("tool pull_request_diff", out)
            self.assertIn("resource notes://style", out)
            status, out = self.run_quiet(mcp_setup.context_test, "code", show=True)
        self.assertEqual(status, 0, out)
        self.assertIn("1 binding(s) match", out)
        self.assertIn("PR #3: + retry the flaky upload (token t-1)", out)
        _, out = self.run_quiet(mcp_setup.context_test, "gedit")
        self.assertIn("0 binding(s) match", out)


if __name__ == "__main__":
    unittest.main()


class AgentConfigTests(unittest.TestCase):
    def test_an_agent_gets_remote_servers_it_can_use_and_no_secrets(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')
        from claudish.model import Rewriter
        from claudish.tools import Toolbox
        servers = {"docs": {"url": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer $DOCS_TOKEN"}},
                   "notes": {"command": "notes-mcp", "env": {"TOKEN": "$NOTES_TOKEN"}}}
        rewriter = Rewriter()
        rewriter.toolbox = Toolbox(["docs", "notes"], servers)
        with patch.dict(os.environ, {"DOCS_TOKEN": "s3cret", "NOTES_TOKEN": "s3cret"}):
            given = rewriter.agent_mcp_config(type("Box", (), {"key": "box", "token": "t"})())["mcpServers"]
        self.assertEqual(given["docs"]["type"], "http")
        self.assertEqual(given["docs"]["headers"], {"Authorization": "Bearer ${DOCS_TOKEN}"})  # Claude Code fills it in
        self.assertEqual(given["notes"]["env"], {"TOKEN": "${NOTES_TOKEN}"})
        self.assertNotIn("s3cret", json.dumps(given))
