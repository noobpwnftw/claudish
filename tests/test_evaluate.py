import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evaluate", ROOT / "benchmarks" / "evaluate.py")
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class EvaluationCheckTests(unittest.TestCase):
    def test_faithful_rewrite_passes(self):
        case = {"text": "Only 3 of the 40 tests failed.", "keep": ["3", "40"]}
        self.assertEqual(evaluate.check(case, "Merely 3 of the 40 tests failed—a modest setback."), [])

    def test_meaning_and_format_failures(self):
        negated = {"text": "Do not merge this yet."}
        self.assertEqual(evaluate.check(negated, "Please merge this at once."), ["negation"])
        self.assertEqual(evaluate.check(negated, "Kindly refrain from merging this for now."), [])
        self.assertEqual(evaluate.check({"text": "Tell Priya.", "keep": ["Priya"]}, "Inform her."),
                         ["missing:Priya"])
        self.assertIn("preamble", evaluate.check({"text": "Sounds good."}, "Sure! That sounds excellent."))
        self.assertIn("quoted", evaluate.check({"text": "Sounds good."}, "“That sounds excellent.”"))
        counted = {"text": "Only 3 of the 40 tests failed.", "keep": ["3", "40"]}
        self.assertEqual(evaluate.check(counted, "Only 3 of 40 failed—three out of four."), ["new-number"])
        self.assertEqual(evaluate.check(counted, "Merely 3 (three) of the 40 tests failed."), [])
        self.assertIn("length", evaluate.check({"text": "The build takes 14 minutes today."}, "Slow."))

    def test_summary_counts_errors_and_unchanged_output(self):
        cases = [{"id": "a", "category": "x", "text": "On it."},
                 {"id": "b", "category": "x", "text": "Thanks!"}]
        report = evaluate.score(cases, [("On it.", None, 10.0), (None, "model busy", 20.0)])
        self.assertEqual((report["faithful"], report["faithful_and_changed"], report["errors"]), (1, 0, 1))

    def test_cases_are_well_formed(self):
        cases = json.loads((ROOT / "benchmarks/eval/cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        for case in cases:
            self.assertTrue(all(item in case["text"] for item in case.get("keep", [])), case["id"])


if __name__ == "__main__":
    unittest.main()
