import json
import unittest

from claudish import shapes

ASK = {"type": "function", "function": {"name": "user__ask", "description": "Ask the user.", "parameters": {
    "type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}}


class ShapeTests(unittest.TestCase):
    """Every answer is {"drafts": [...]}; on a server held to a schema, tool calls are steps of it."""

    def test_a_step_is_a_call_with_its_own_arguments_or_the_answer(self):
        schema = shapes.step_format([ASK])["json_schema"]["schema"]["anyOf"]
        self.assertEqual(schema[0]["properties"]["call"], {"const": "user__ask"})
        self.assertEqual(schema[0]["properties"]["arguments"]["required"], ["question"])  # the tool's own
        self.assertEqual(schema[-1], shapes.ANSWER)
        odd = dict(ASK, function=dict(ASK["function"], name="x", parameters={"$ref": "#/defs/y"}))
        self.assertEqual(shapes.step_format([odd])["json_schema"]["schema"]["anyOf"][0]["properties"]["arguments"],
                         shapes.OBJECT)  # a schema a grammar cannot hold: any object

    def test_steps_and_tool_calls_turn_into_each_other(self):
        call = shapes.as_message(json.dumps({"call": "user__ask", "arguments": {"question": "Which?"}}), 3)
        function = call["tool_calls"][0]["function"]
        self.assertEqual((function["name"], json.loads(function["arguments"])), ("user__ask", {"question": "Which?"}))
        history = shapes.as_steps(shapes.as_answered([
            {"role": "system", "content": "s"}, {"role": "user", "content": "go"}, dict(call, role="assistant"),
            {"role": "tool", "tool_call_id": "step-3", "content": "The user chose: A"},
            {"role": "assistant", "content": "Done."}]))
        self.assertEqual(json.loads(history[2]["content"]), {"call": "user__ask", "arguments": {"question": "Which?"}})
        self.assertEqual(history[3], {"role": "user", "content": "Result of user__ask:\nThe user chose: A"})
        self.assertEqual(json.loads(history[4]["content"]), {"drafts": ["Done."]})  # an earlier answer, as answered
        answer = shapes.as_message('{"drafts": ["Hi!", "Hello!"]}')
        self.assertEqual(shapes.drafts(answer["content"]), ["Hi!", "Hello!"])

    def test_drafts_or_none(self):
        self.assertEqual(shapes.drafts('{"drafts": ["  a  ", "", 3, "b"]}'), ["a", "b"])
        self.assertEqual(shapes.drafts({"drafts": ["x"]}), ["x"])
        for plain in ("Absolutely!", '{"text": "x"}', '{"drafts": []}', ""):
            self.assertIsNone(shapes.drafts(plain))

    def test_tools_are_described_to_the_model(self):
        told = shapes.with_tools([{"role": "system", "content": "Write."}, {"role": "user", "content": "go"}], [ASK],
                                 "Tools:")
        self.assertEqual(told[0]["content"], "Write.\n\nTools:\n- user__ask: Ask the user.")
        self.assertEqual(told[1], {"role": "user", "content": "go"})


class ServerShapeTests(unittest.TestCase):
    """A model server held to the schema, and one that refuses it."""

    def answers(self, *replies):
        from io import BytesIO
        from urllib.error import HTTPError
        from claudish.model import Rewriter
        rewriter, sent = Rewriter(max_tokens=64), []

        def chat(payload, headers, image=None, timeout=None):
            sent.append(payload)
            reply = replies[min(len(sent), len(replies)) - 1]
            if isinstance(reply, int):
                raise HTTPError("u", reply, "no", {}, BytesIO(b""))
            return {"message": {"content": reply}, "finish_reason": "stop"}, {}
        rewriter.chat = chat
        return rewriter, sent

    def test_an_example_answer_given_back_is_not_offered(self):
        from claudish.model import Rewriter
        rewriter, _ = self.answers(shapes.example(Rewriter("rules").modes["instruct"]["examples"][1]["content"]))
        with self.assertRaisesRegex(RuntimeError, "offered nothing"):
            rewriter.rewrite("tttt", mode="instruct")  # nonsense in, the template's own example out

    def test_several_drafts_take_one_reading(self):
        rewriter, sent = self.answers('{"drafts": ["One.", "Two.", "Three."]}')
        self.assertEqual(rewriter.rewrite("three ways to say thanks", mode="instruct")["candidates"],
                         ["One.", "Two.", "Three."])
        self.assertEqual(len(sent), 1)

    def test_a_follow_up_names_the_draft_in_view_and_every_draft_is_remembered(self):
        from claudish.conversation import Conversation
        rewriter, sent = self.answers('{"drafts": ["One—yes.", "Two—indeed."]}', '{"drafts": ["Two."]}')
        conversation = Conversation("box")
        rewriter.answer("instruct", "two ways to agree", rewriter.box("instruct"), conversation=conversation)
        self.assertEqual(shapes.drafts(conversation.messages[1]["content"]), ["One—yes.", "Two—indeed."])
        box = rewriter.box("instruct")
        box.draft = "Two—indeed."
        rewriter.answer("instruct", "shorter", box, conversation=conversation)
        turn = sent[-1]["messages"][-1]["content"]
        self.assertIn("Two—indeed.", turn)
        self.assertTrue(turn.rstrip().endswith("shorter"))
        self.assertEqual(conversation.messages[2], {"role": "user", "content": "shorter"})  # as typed

    def test_a_refused_schema_asks_the_turn_again_in_plain_text(self):
        rewriter, sent = self.answers(400, "Hello there—synergy!")
        self.assertEqual(rewriter.rewrite("hi")["text"], "Hello there—synergy!")
        self.assertNotIn("response_format", sent[1])
        self.assertNotIn('{"drafts"', json.dumps(sent[1]["messages"]))  # no shape left in the prompt
        self.assertFalse(rewriter.schema)

    def test_refused_plain_too_the_schema_stays(self):
        rewriter, _ = self.answers(400, 400)
        with self.assertRaises(Exception):
            rewriter.rewrite("hi")
        self.assertTrue(rewriter.schema)


class AgentShapeTests(unittest.TestCase):
    def test_claude_code_is_held_to_the_schema(self):
        from claudish.warm import ClaudeCode
        code = ClaudeCode(["claude"])
        argv = code.argv()
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), shapes.ANSWER)
        self.assertTrue(code.shaped)

    def test_a_codex_turn_is_held_to_the_schema(self):
        from claudish.warm import Codex
        codex, sent = Codex(["codex"]), {}

        def call(method, params, deadline, collect=None):
            sent[method] = params
            if method == "turn/start":
                collect({"method": "item/completed", "params": {"item": {"type": "agentMessage",
                                                                         "text": '{"drafts": ["Hi!"]}'}}})
                collect({"method": "turn/completed", "params": {"turn": {}}})
            return {"thread": {"id": "t1"}}
        codex.call = call
        self.assertEqual(shapes.drafts(codex.exchange("hi", 5)), ["Hi!"])
        self.assertEqual(sent["turn/start"]["outputSchema"], shapes.ANSWER)
        self.assertTrue(codex.shaped)


if __name__ == "__main__":
    unittest.main()
