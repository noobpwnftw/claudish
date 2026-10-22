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
        self.assertEqual(servers["notes"]["env"], {"TEST_TOKEN": "$MY_TOKEN"})
        self.assertEqual(servers["remote"], {"url": "https://sse.example.com/sse", "type": "sse",
                                             "headers": {"X-Key": "$REMOTE_KEY"}})
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
        data["profiles"]["local"]["bindings"] = [{"app": "code", "context": [
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
