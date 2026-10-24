import json
import sys
import unittest
from pathlib import Path

SERVER = {"notes": {"command": sys.executable, "args": [str(Path(__file__).with_name("mcp_server.py"))]}}


def call(name, **arguments):
    return {"id": "c-" + name, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


class ToolLoopTests(unittest.TestCase):
    """A scripted model drives the loop against a real stdio MCP server (tests/mcp_server.py)."""

    def setUp(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')

    def run_loop(self, replies, trust=()):
        from claudish.tools import Toolbox
        seen = []

        def ask(messages, tools):
            seen.append((list(messages), tools))
            return replies[len(seen) - 1]
        toolbox = Toolbox([{"server": "notes", "trust": list(trust)}], SERVER, timeout=30)
        text, consulted, _ = toolbox.run(ask, [{"role": "user", "content": "summarize CI for main"}])
        return text, consulted, seen

    def test_read_only_tools_are_offered_and_called(self):
        text, consulted, seen = self.run_loop([
            {"content": "", "tool_calls": [call("notes__ci_status", branch="main")]},
            {"content": "CI on main: one flaky upload test—otherwise green."}])
        offered = sorted(tool["function"]["name"] for tool in seen[0][1])
        self.assertEqual(offered, ["notes__ci_status"])  # unannotated and destructive tools are not offered
        self.assertEqual(text, "CI on main: one flaky upload test—otherwise green.")
        self.assertEqual(consulted, ['notes.ci_status(branch="main")'])
        tool_message = seen[1][0][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertIn("test_upload_retry", tool_message["content"])

    def test_trust_adds_a_tool_and_side_effects_are_refused(self):
        text, consulted, seen = self.run_loop([
            {"content": "", "tool_calls": [call("notes__delete_branch", branch="main"),
                                            call("notes__pull_request_diff", number=3)]},
            {"content": "Done."}], trust=["pull_request_diff"])
        self.assertEqual(sorted(t["function"]["name"] for t in seen[0][1]),
                         ["notes__ci_status", "notes__pull_request_diff"])
        results = [m["content"] for m in seen[1][0] if m["role"] == "tool"]
        self.assertEqual(results[0], "error: unknown tool or invalid arguments")  # never reached the server
        self.assertIn("PR #3", results[1])
        self.assertEqual(consulted, ["notes.pull_request_diff(number=3)"])

    def test_the_loop_is_bounded(self):
        from claudish.tools import MAX_STEPS
        endless = [{"content": "", "tool_calls": [call("notes__ci_status", branch="x")]}] * MAX_STEPS
        text, consulted, seen = self.run_loop(endless + [{"content": "Out of steps—here is what I have."}])
        self.assertEqual(len(seen), MAX_STEPS + 1)
        self.assertIsNone(seen[-1][1])  # the last turn gets no tools: it must answer
        self.assertEqual(text, "Out of steps—here is what I have.")

    def test_config_errors(self):
        from claudish.tools import Toolbox
        with self.assertRaisesRegex(ValueError, "not in"):
            Toolbox(["missing"], SERVER)
        with self.assertRaisesRegex(ValueError, "server names"):
            Toolbox([{"server": "notes", "allow": []}], SERVER)  # an unknown key


class RewriterTests(unittest.TestCase):
    def setUp(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')

    def settings(self, **profile):
        import tempfile
        from claudish import config
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name, "config.json")
        path.write_text(json.dumps({"mcp_servers": SERVER, "profiles": {"p": dict({"backend": "llama", "tools": ["notes"]}, **profile)}}))
        return config.resolve(path)

    def test_instructions_use_the_loop_and_list_the_calls(self):
        from unittest.mock import patch
        from claudish.model import Rewriter
        _, settings, prompt, context = self.settings()
        rewriter = Rewriter.from_settings(settings, prompt, context)
        with patch.object(rewriter.toolbox, "run", return_value=("CI is green.", ['notes.ci_status(branch="main")'], [])) as run:
            result = rewriter.rewrite("how is CI", mode="instruct")
        self.assertEqual((result["text"], result["candidates"]), ("CI is green.", ["CI is green."]))
        self.assertIn('notes.ci_status(branch="main")', result["consulted"])
        self.assertIn("never invent", run.call_args.args[1][0]["content"])
        with patch.object(rewriter, "opener") as opener, patch.object(rewriter.toolbox, "run") as run:
            opener.open.return_value = __import__("io").BytesIO(json.dumps(
                {"choices": [{"message": {"content": "Very good."}, "finish_reason": "stop"}]}).encode())
            rewriter.rewrite("good")  # a rewrite never starts the tool loop
            run.assert_not_called()

    def test_tools_need_a_backend_with_tool_calls(self):
        from claudish.model import Rewriter
        _, settings, prompt, context = self.settings(backend="command", command=["cat"])
        with self.assertRaisesRegex(ValueError, "cannot use them"):
            Rewriter.from_settings(settings, prompt, context)


if __name__ == "__main__":
    unittest.main()
