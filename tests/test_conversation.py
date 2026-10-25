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
            self.assertEqual([c["label"] for c in question["choices"]], ["Deny", "Allow", "Allow for this conversation"])
            self.assertIn("pull_request_diff(number=3)", question["body"])  # what is approved, in full
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

    def test_an_unanswered_question_ends_the_instruction(self):
        """A model told "no answer" asks again: the instruction stops instead of holding its session."""
        again = answer(calls=[("user__ask", {"question": "Shall I?"})])
        model = Scripted(again, again, again, again, again)
        with patch("claudish.conversation.QUESTION_SECONDS", 0.2):
            asked, result = self.drive(model, [])
        self.assertEqual((result["type"], result["text"]), ("error", "no answer, so the instruction stopped"))
        self.assertLessEqual(len(model.sent), 2)  # it stops at the next call, not after every round

    def test_at_a_terminal_prompt_the_helper_is_a_command_to_run(self):
        """In a terminal the handoff is a draft at the prompt: Tab puts it there and your Enter runs
        it in that folder; no window opens and nothing is asked."""
        import os
        import tempfile
        model = Scripted(answer(calls=[("helper__claude", {"task": "Find why the tests fail and fix it"})]))
        with patch("claudish.handoff.shutil.which", return_value="/bin/claude"), \
                patch("claudish.handoff.launch") as launch, \
                patch.dict(os.environ, {"XDG_RUNTIME_DIR": tempfile.mkdtemp()}):
            asked, result = self.drive(model, [], helper=["claude", "--session-id", "{session}", "{prompt}"],
                                       purpose="terminal", screen="$ python3 -m unittest\nFAILED (failures=1)\n$ ")
        launch.assert_not_called()
        self.assertEqual(asked, [])
        command = result["text"]
        self.assertEqual(result["candidates"], [command])
        self.assertTrue(command.startswith("claude --session-id "), command)
        self.assertIn("handoff", command)  # the note with the task and the screen

    def test_a_helper_takes_the_task_after_a_yes_in_any_text_box(self):
        import os
        import tempfile
        model = Scripted(answer(calls=[("helper__claude", {"task": "Find why the build fails and fix it"})]))
        folder = tempfile.mkdtemp()
        with patch("claudish.handoff.shutil.which", return_value="/bin/claude"), \
                patch("claudish.handoff.launch", return_value=True) as launch, \
                patch.dict(os.environ, {"XDG_RUNTIME_DIR": folder}):
            asked, result = self.drive(model, [1], helper=["claude", "{prompt}"], before="Hi team, the build ")
        # The whole task is in the question: nothing the helper is told is hidden. The safe choice
        # is 1 (No): a reflexive 1 never hands anything over.
        self.assertEqual((asked[0]["label"], asked[0]["body"]), ("Hand off to Claude Code", "Find why the build fails and fix it"))
        self.assertEqual([c["label"] for c in asked[0]["choices"]], ["No", "Yes"])
        self.assertEqual((result["text"], result["candidates"], result["done"]),
                         ("", [], "claude opened in a new window"))
        template, note, launcher, session, window = launch.call_args.args
        self.assertIsNone(launcher)
        self.assertEqual(session, "")  # no {session} in the template: nothing to follow up on
        self.assertEqual(template, ["claude", "{prompt}"])
        self.assertTrue(note.startswith(folder))
        if os.name == "posix":
            self.assertEqual(os.stat(note).st_mode & 0o777, 0o600)
        self.assertIn("Find why the build fails and fix it", Path(note).read_text(encoding="utf-8"))

    def test_no_to_the_helper_lets_the_model_answer(self):
        model = Scripted(answer(calls=[("helper__claude", {"task": "fix the build"})]), answer("make clean && make"))
        with patch("claudish.handoff.shutil.which", return_value="/bin/claude"), \
                patch("claudish.handoff.launch") as launch:
            asked, result = self.drive(model, [0], helper=["claude", "{prompt}"])  # 1 on screen: No
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
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}), \
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
        model = Scripted(answer(calls=[("user__show", {"answer": "The linker cannot find tokenize: add tokenize.o."})]))
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
        model = Scripted(answer(calls=[("user__show", {"answer": "make clean\nmake"})]))
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


class FollowUpTests(unittest.TestCase):
    def test_a_shown_answer_stays_in_the_conversation_for_the_next_instruction(self):
        """"What does this error mean?", read and dismissed, then "well then fix it for me" in the
        same box: the second turn sees the first, so "it" is known."""
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        conversation = rewriter.conversations.get("term")
        # No "OK" round after the answer: choosing ends the turn, and the conversation keeps it.
        model = Scripted(answer(calls=[("user__show", {"answer": "The linker cannot find tokenize."})]),
                         answer("cc -o app main.o parse.o tokenize.o"))
        with patch.object(rewriter, "chat", model):
            for text, choice in (("what does this error mean", 1), ("well then fix it for me", None)):
                session, thread = run(ModelDriver(rewriter, conversation, purpose="terminal",
                                                  screen="$ make\nundefined reference to `tokenize'\n$"), text)
                if choice is not None:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline and not any(e["type"] == "question" for e in session.events):
                        time.sleep(0.01)
                    session.answer(next(e for e in session.events if e["type"] == "question")["id"], choice)
                thread.join(5)
        later = json.dumps(model.sent[-1]["messages"])
        self.assertIn("what does this error mean", later)
        self.assertIn("The linker cannot find tokenize.", later)  # what was shown, though dismissed
        self.assertIn("they dismissed it", later)
        self.assertEqual(len(model.sent), 2)  # one call per turn
        self.assertEqual(session.events[-1]["text"], "cc -o app main.o parse.o tokenize.o")


class HandleTests(unittest.TestCase):
    """G44: after a handoff, "is it done?" in the same box reads the helper's own transcript."""

    def test_is_it_done_reads_the_helpers_session(self):
        import os
        import tempfile
        rewriter = Rewriter()
        rewriter.modes["instruct"]["candidates"] = 1
        rewriter.helper = ["claude", "--session-id", "{session}", "{prompt}"]
        conversation = rewriter.conversations.get("term")
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home, "USERPROFILE": home, "XDG_RUNTIME_DIR": home}), \
                patch("claudish.handoff.shutil.which", return_value="/bin/claude"), \
                patch("claudish.handoff.launch", return_value=True) as launch:
            model = Scripted(answer(calls=[("helper__claude", {"task": "Fix the link error"})]))
            with patch.object(rewriter, "chat", model):
                session, thread = run(ModelDriver(rewriter, conversation), "have claude fix the build")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and not any(e["type"] == "question" for e in session.events):
                    time.sleep(0.01)
                session.answer(next(e for e in session.events if e["type"] == "question")["id"], 1)  # Yes
                thread.join(5)
            helper_session = launch.call_args.args[3]
            self.assertTrue(helper_session)  # Claude Code is started with an id Claudish chose
            # Claude Code writes its transcript under ~/.claude/projects/<cwd as dashes>/<session>.jsonl.
            folder = os.path.join(home, ".claude", "projects", "".join(c if c.isalnum() else "-" for c in home))
            os.makedirs(folder)
            with open(os.path.join(folder, helper_session + ".jsonl"), "w") as out:
                out.write(json.dumps({"type": "assistant", "timestamp": "2026-10-23T12:00:00Z", "message": {
                    "content": [{"type": "tool_use", "name": "Edit"}]}}) + "\n")
                out.write(json.dumps({"type": "assistant", "timestamp": "2026-10-23T12:01:00Z", "message": {
                    "content": [{"type": "text", "text": "Added tokenize.o to the Makefile; the build passes."}]}}) + "\n")
            model = Scripted(answer(calls=[("helper__check", {})]), answer("Yes: the build passes now."))
            with patch.object(rewriter, "chat", model):
                session, thread = run(ModelDriver(rewriter, conversation), "is it done?")
                thread.join(5)
        offered = [tool["function"]["name"] for tool in model.sent[0]["tools"]]
        self.assertIn("helper__check", offered)
        checked = model.sent[1]["messages"][-1]["content"]
        self.assertIn("Added tokenize.o to the Makefile; the build passes.", checked)
        self.assertIn("(used Edit)", checked)
        self.assertEqual(session.events[-1]["text"], "Yes: the build passes now.")


class TmuxHandleTests(unittest.TestCase):
    def test_a_named_tmux_window_is_read_for_any_helper(self):
        import shutil
        import subprocess
        from claudish import handoff
        if not shutil.which("tmux"):
            self.skipTest("no tmux")
        name = "claudish-test-%d" % (time.time() * 1000 % 100000)
        subprocess.run(["tmux", "new-session", "-d", "-s", name, "printf 'building\\nAPI_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\\nall tests pass\\n'; sleep 5"],
                       check=True)
        try:
            deadline, text = time.monotonic() + 3, ""
            while "all tests pass" not in text and time.monotonic() < deadline:  # drawn when tmux gets to it
                time.sleep(0.05)
                text = handoff.progress({"helper": "aider", "task": "fix it", "tmux": name, "started": time.time(), "cwd": "/"})
        finally:
            subprocess.run(["tmux", "kill-session", "-t", name])
        self.assertIn("all tests pass", text)
        self.assertNotIn("sk-abc", text)  # redacted, like a terminal screen


if __name__ == "__main__":
    unittest.main()
