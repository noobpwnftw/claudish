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
        history = shapes.as_steps([{"role": "system", "content": "s"}, {"role": "user", "content": "go"},
                                   dict(call, role="assistant"),
                                   {"role": "tool", "tool_call_id": "step-3", "content": "The user chose: A"},
                                   {"role": "assistant", "content": "Done."}])
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
