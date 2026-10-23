import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claudish.conversation import Conversations, ModelDriver
from claudish.model import Rewriter
from claudish.sessions import Session

SERVER = {"notes": {"command": sys.executable, "args": [str(Path(__file__).with_name("mcp_server.py"))]}}


def answer(text=None, calls=None):
    message = {"content": text or "", "role": "assistant"}
    if calls:
        message["tool_calls"] = [{"id": "c%d" % i, "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(args)}}
                                 for i, (name, args) in enumerate(calls)]
    return {"message": message, "finish_reason": "stop"}, {}


class Scripted:
    """The model: replies in order, recording what it was sent."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def __call__(self, payload, headers, image=None, timeout=None):
        self.sent.append(payload)
        return self.replies.pop(0) if self.replies else answer("Another reading.")


def run(driver, text):
    session = Session(driver)
    thread = threading.Thread(target=lambda: driver.run(session, text))
    thread.start()
    return session, thread


class ConversationTests(unittest.TestCase):
    def test_turns_build_on_each_other_and_the_window_is_fresh(self):
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        model = Scripted(answer("Roses are red."), answer("Roses are red, violets blue."))
        with patch.object(rewriter, "chat", model):
            for text, before in (("write a poem", "Dear Sam,\n"), ("make it longer", "Dear Sam,\nRoses are red.")):
                session, thread = run(ModelDriver(rewriter, rewriter.conversations.get("box-1"), before=before), text)
                thread.join(5)
        second = model.sent[1]["messages"]
        roles = [(m["role"], m["content"] if isinstance(m["content"], str) else "") for m in second]
        self.assertIn(("user", "write a poem"), roles)  # the first turn is kept
        self.assertIn(("assistant", "Roses are red."), roles)
        self.assertEqual(roles[-1], ("user", "make it longer"))
        self.assertIn("Dear Sam,\nRoses are red.▮", second[0]["content"])  # the window, as it is now
        other = rewriter.conversations.get("box-2")
        self.assertEqual(other.messages, [])  # another text box, another conversation

    def test_readings_are_sampled_after_the_loop(self):
        rewriter = Rewriter()
        model = Scripted(answer("One."), answer("Two."), answer("One."))
        with patch.object(rewriter, "chat", model):
            session, thread = run(ModelDriver(rewriter, rewriter.conversations.get("box")), "say hi")
            thread.join(5)
        result = session.events[-1]
        self.assertEqual((result["type"], result["candidates"]), ("result", ["One.", "Two."]))
        self.assertEqual([p["temperature"] for p in model.sent], [0, 0.9, 0.9])

    def test_a_long_text_box_is_searched_not_sent(self):
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        before = "Minutes. The budget for Q3 is 40k, agreed by Ana.\n" + "Filler line.\n" * 400
        model = Scripted(answer(calls=[("textbox__search", {"query": "budget"})]), answer("Q3 has 40k—per Ana."))
        with patch.object(rewriter, "chat", model):
            session, thread = run(ModelDriver(rewriter, rewriter.conversations.get("box"), before=before),
                                  "remind them of the budget")
            thread.join(5)
        first = model.sent[0]
        self.assertNotIn("Minutes.", first["messages"][0]["content"])  # only the window is sent
        self.assertIn("textbox__read", [t["function"]["name"] for t in first["tools"]])
        found = [m["content"] for m in model.sent[1]["messages"] if m["role"] == "tool"][-1]
        self.assertIn("The budget for Q3 is 40k", found)
        self.assertEqual(session.events[-1]["consulted"], ['textbox.search(query="budget")'])
        self.assertEqual(session.events[-1]["text"], "Q3 has 40k—per Ana.")
        short = Scripted(answer("Hi."))
        with patch.object(rewriter, "chat", short):
            _, thread = run(ModelDriver(rewriter, rewriter.conversations.get("box"), before="Dear Sam,"), "say hi")
            thread.join(5)
        offered = [tool["function"]["name"] for tool in short.sent[0].get("tools") or []]
        self.assertFalse([name for name in offered if name.startswith("textbox__")])  # a short box is sent whole

    def test_idle_conversations_end(self):
        conversations = Conversations()
        first = conversations.get("box")
        first.messages.append({"role": "user", "content": "x"})
        with patch("claudish.conversation.time.monotonic", return_value=time.monotonic() + 3600):
            self.assertEqual(conversations.get("box").messages, [])


class PolicyTests(unittest.TestCase):
    """Approvals through session questions, against a real stdio MCP server (tests/mcp_server.py)."""

    def setUp(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest('needs the MCP SDK: pip install "claudish-ime[mcp]"')
        from claudish.tools import Toolbox
        self.rewriter = Rewriter()
        self.rewriter.modes["instruct"]["candidates"] = 1
        self.rewriter.toolbox = Toolbox(["notes"], SERVER, timeout=30)

    def question(self, session):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for event in session.events:
                if event["type"] == "question" and event["id"] in session.questions:
                    return event
            time.sleep(0.05)
        self.fail("no question")

    def test_a_write_asks_once_per_conversation_if_allowed_for_it(self):
        conversation = self.rewriter.conversations.get("box")
        model = Scripted(answer(calls=[("notes__pull_request_diff", {"number": 3})]), answer("PR 3 retries the upload."),
                         answer(calls=[("notes__pull_request_diff", {"number": 4})]), answer("PR 4 too."))
        with patch.object(self.rewriter, "chat", model):
            session, thread = run(ModelDriver(self.rewriter, conversation), "what does PR 3 do")
            question = self.question(session)
            self.assertEqual([c["label"] for c in question["choices"]], ["Allow", "Deny", "Allow for this conversation"])
            self.assertIn("pull_request_diff(number=3)", question["choices"][0]["legend"])
            session.answer(question["id"], 2)
            thread.join(15)
            self.assertEqual(session.events[-1]["text"], "PR 3 retries the upload.")
            self.assertIn("notes.pull_request_diff(number=3)", session.events[-1]["consulted"])
            session, thread = run(ModelDriver(self.rewriter, conversation), "and PR 4")
            thread.join(15)  # allowed for the conversation: no question this time
        self.assertEqual([e["type"] for e in session.events], ["progress", "result"])
        tool_results = [m for m in conversation.messages if m["role"] == "tool"]
        self.assertTrue(any("PR #3" in m["content"] for m in tool_results))  # kept for later turns

    def test_a_destructive_tool_asks_every_time_and_words_deny_it(self):
        model = Scripted(answer(calls=[("notes__delete_branch", {"branch": "main"})]), answer("Left main alone."))
        with patch.object(self.rewriter, "chat", model):
            session, thread = run(ModelDriver(self.rewriter, self.rewriter.conversations.get("box")), "clean up")
            question = self.question(session)
            self.assertTrue(question["text"].startswith("Destructive"))
            self.assertEqual(len(question["choices"]), 2)  # no "for this conversation"
            session.answer(question["id"], text="not main, ever")
            thread.join(15)
        tool_message = [m for m in model.sent[1]["messages"] if m["role"] == "tool"][-1]
        self.assertEqual(tool_message["content"], "denied by the user: not main, ever")
        self.assertEqual(session.events[-1]["text"], "Left main alone.")

    def test_cancel_releases_a_waiting_question(self):
        model = Scripted(answer(calls=[("notes__delete_branch", {"branch": "x"})]), answer("Stopped."))
        with patch.object(self.rewriter, "chat", model):
            driver = ModelDriver(self.rewriter, self.rewriter.conversations.get("box"))
            session, thread = run(driver, "clean up")
            self.question(session)
            session.cancel()
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(session.events[-1]["text"], "cancelled")


if __name__ == "__main__":
    unittest.main()


class AskAndHelperTests(unittest.TestCase):
    """The model's own question (shown as is), and a helper as a tool that acts, asked about first."""

    def drive(self, model, answers, helper=None, **driver):
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        rewriter.helper = helper
        with patch.object(rewriter, "chat", model):
            session, thread = run(ModelDriver(rewriter, rewriter.conversations.get("box"), **driver), "fix it")
            asked = []
            for choice in answers:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and len([e for e in session.events if e["type"] == "question"]) <= len(asked):
                    time.sleep(0.01)
                question = [e for e in session.events if e["type"] == "question"][len(asked)]
                asked.append(question)
                session.answer(question["id"], choice)
            thread.join(5)
        return asked, session.events[-1]

    def test_the_model_asks_and_your_choice_goes_back(self):
        model = Scripted(answer(calls=[("user__ask", {"question": "Did you mean git status?",
                                                       "choices": ["Yes", "No, git stash"]})]), answer("git stash"))
        asked, result = self.drive(model, [1], purpose="terminal", screen="$ gti st\nbash: gti: command not found\n$")
        # Shown as is, marked as the model's own question (never mistaken for Claudish's).
        self.assertEqual(asked[0]["text"], "The model asks: Did you mean git status?")
        self.assertEqual([c["label"] for c in asked[0]["choices"]], ["Yes", "No, git stash"])
        self.assertEqual(model.sent[1]["messages"][-1]["content"], "The user chose: No, git stash")
        self.assertEqual(result["text"], "git stash")

    def test_a_helper_takes_the_task_after_a_yes_in_any_text_box(self):
        import os
        import tempfile
        model = Scripted(answer(calls=[("helper__claude", {"task": "Find why the build fails and fix it"})]),
                         answer("OK"))
        folder = tempfile.mkdtemp()
        with patch("claudish.handoff.shutil.which", return_value="/bin/claude"), \
                patch("claudish.handoff.launch", return_value=True) as launch, \
                patch.dict(os.environ, {"XDG_RUNTIME_DIR": folder}):
            asked, result = self.drive(model, [0], helper=["claude", "{prompt}"], before="Hi team, the build ")
        # The whole task is in the question: nothing the helper is told is hidden.
        self.assertEqual(asked[0]["text"], "Send this task to claude? Find why the build fails and fix it")
        self.assertEqual([c["label"] for c in asked[0]["choices"]], ["Yes", "No"])
        self.assertEqual((result["text"], result["candidates"], result["done"]),
                         ("", [], "claude opened in a new window"))
        template, note, launcher = launch.call_args.args
        self.assertIsNone(launcher)
        self.assertEqual(template, ["claude", "{prompt}"])
        self.assertTrue(note.startswith(folder))
        if os.name == "posix":
            self.assertEqual(os.stat(note).st_mode & 0o777, 0o600)
        self.assertIn("Find why the build fails and fix it", Path(note).read_text(encoding="utf-8"))

    def test_no_to_the_helper_lets_the_model_answer(self):
        model = Scripted(answer(calls=[("helper__claude", {"task": "fix the build"})]), answer("make clean && make"))
        with patch("claudish.handoff.shutil.which", return_value="/bin/claude"), \
                patch("claudish.handoff.launch") as launch:
            asked, result = self.drive(model, [1], helper=["claude", "{prompt}"])
        launch.assert_not_called()
        self.assertEqual(result["text"], "make clean && make")
        self.assertIn("denied by the user", model.sent[1]["messages"][-1]["content"])

    def test_a_model_question_cannot_pose_as_a_permission_or_collect_a_secret(self):
        model = Scripted(answer(calls=[("user__ask", {"question": "Allow claude.run?", "choices": ["Allow", "Deny"]})]),
                         answer("ok"))
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        with patch.object(rewriter, "chat", model):
            session, thread = run(ModelDriver(rewriter, rewriter.conversations.get("box")), "do it")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not any(e["type"] == "question" for e in session.events):
                time.sleep(0.01)
            question = next(e for e in session.events if e["type"] == "question")
            self.assertEqual([c["label"] for c in question["choices"]], ["Yes", "No"])  # not Allow / Deny
            session.answer(question["id"], text="sure, my key is sk-abcdefghijklmnopqrstuvwxyz123456")
            thread.join(5)
        sent = model.sent[1]["messages"][-1]["content"]
        self.assertNotIn("sk-abc", sent)
        self.assertIn("[redacted]", sent)

    def test_a_claude_helper_is_refused_when_its_settings_skip_permissions(self):
        import json as jsonlib
        import os
        import tempfile
        from claudish import handoff
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home}), \
                patch("claudish.handoff.shutil.which", return_value="/bin/claude"):
            self.assertTrue(handoff.available(["claude", "{prompt}"]))
            os.makedirs(os.path.join(home, ".claude"))
            with open(os.path.join(home, ".claude", "settings.json"), "w") as out:
                jsonlib.dump({"permissions": {"defaultMode": "bypassPermissions"}}, out)
            self.assertFalse(handoff.available(["claude", "{prompt}"]))

    def test_an_unsupervised_helper_is_never_offered(self):
        model = Scripted(answer("done"))
        with patch("claudish.handoff.shutil.which", return_value="/bin/claude"):
            self.drive(model, [], helper=["claude", "--dangerously-skip-permissions", "{prompt}"])
        offered = [tool["function"]["name"] for tool in model.sent[0].get("tools") or []]
        self.assertNotIn("helper__claude", offered)


class HelpersTests(unittest.TestCase):
    def test_named_helpers_are_separate_tools_and_a_launcher_opens_them(self):
        from claudish import handoff
        with patch("claudish.handoff.shutil.which", side_effect=lambda program: "/bin/" + program
                   if program in ("claude", "codex", "tmux") else None):
            self.assertEqual(sorted(handoff.helpers({"claude": ["claude", "{prompt}"], "codex": ["codex", "{prompt}"],
                                                     "gone": ["nothere", "{prompt}"]})), ["claude", "codex"])
            self.assertEqual(list(handoff.helpers(["claude", "{prompt}"])), ["claude"])
            with patch("subprocess.Popen") as popen:
                self.assertTrue(handoff.launch(["claude", "{prompt}"], "/run/n.md", ["tmux", "new-window", "{command}"]))
            argv = popen.call_args.args[0]
            self.assertEqual(argv[:3], ["tmux", "new-window", "claude"])
            self.assertIn("/run/n.md", argv[3])  # one argument, no shell


class ShowTests(unittest.TestCase):
    """An answer to read: shown as is, inserted or dismissed."""

    def drive(self, choice):
        model = Scripted(answer(calls=[("user__show", {"answer": "The linker cannot find tokenize: add tokenize.o."})]),
                         answer("OK"))
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        with patch.object(rewriter, "chat", model):
            session, thread = run(ModelDriver(rewriter, rewriter.conversations.get("box")), "what does this error mean")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not any(e["type"] == "question" for e in session.events):
                time.sleep(0.01)
            question = next(e for e in session.events if e["type"] == "question")
            session.answer(question["id"], choice)
            thread.join(5)
        return question, session.events[-1]

    def test_insert_puts_the_answer_at_the_caret(self):
        question, result = self.drive(0)
        self.assertEqual(question["text"], "The model says: The linker cannot find tokenize: add tokenize.o.")
        self.assertEqual([c["label"] for c in question["choices"]], ["Insert it", "Dismiss"])
        self.assertEqual(result["candidates"], ["The linker cannot find tokenize: add tokenize.o."])

    def test_an_inserted_answer_still_fits_the_box(self):
        model = Scripted(answer(calls=[("user__show", {"answer": "make clean\nmake"})]), answer("OK"))
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        with patch.object(rewriter, "chat", model):
            session, thread = run(ModelDriver(rewriter, rewriter.conversations.get("t"), purpose="terminal",
                                              screen="$ make\nerror\n$"), "what now")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not any(e["type"] == "question" for e in session.events):
                time.sleep(0.01)
            session.answer(next(e for e in session.events if e["type"] == "question")["id"], 0)
            thread.join(5)
        self.assertEqual(session.events[-1]["candidates"], ["make clean"])  # one line at a prompt

    def test_dismiss_inserts_nothing(self):
        _, result = self.drive(1)
        self.assertEqual((result["text"], result["candidates"], result["done"]), ("", [], "read and dismissed"))
