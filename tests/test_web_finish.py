"""The static demo's copy of modes.finish (claudish/web/browser.js) answers as the service's."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from claudish import modes

BROWSER = Path(__file__).resolve().parents[1] / "claudish/web/browser.js"
RUN = """
const src = require("fs").readFileSync(process.argv[1], "utf8");
const finish = new Function(src.slice(src.indexOf("const WIDE"), src.indexOf("\\n}\\n", src.indexOf("function finish")) + 3)
                            + "; return finish;")();
console.log(JSON.stringify(JSON.parse(process.argv[2]).map(([text, output]) => finish("continue", text, output))));
"""
CASES = [["我今天", "我今天去了商店。"], ["日本", "日本語を勉強"], ["I", "In fact, yes"], ["We", "We're aligned"], ["aligned\u2014", "fully"], ['He said "', "hello"],
         ["(", "see below"], ["caf", "\u0301 time"], ["I ", "in fact, we are thrilled."], ["A ", "As a team, we ship."], ['She said "we are ', 'ready to launch."'],
         ["Dear Sam,", '"I hope this finds you well."'], ["hello ", "Hello, how are you today?"],
         ["Thanks for", "Thanks for the review."], ["我今天", "去了商店。"], ["It works", "—mostly."], ["Thanks", "  "],
         ["Shipped it 🎉", "See you tomorrow."], ["Great", "👍 thanks"], ["ｱｲｳ", "test"], ["ok", "ﾃｽﾄ"], ["안녕하세요", "반갑습니다."],
         ["コーヒー", "Good"], ["ㄅㄆ", "x"], ["ꀀ", "x"], ["ﾡ", "x"],
         ["か\u3099", "x"], ["﹐", "x"], ["㈠", "x"]]


def wide_ranges():
    """modes.finish's rule, over every code point, as the class browser.js's WIDE writes it."""
    import unicodedata
    ranges, start = [], None
    for point in range(0x110000):
        char = chr(point)
        wide = not 0xD800 <= point <= 0xDFFF and unicodedata.east_asian_width(char) in "WFH" \
            and not unicodedata.category(char).startswith("S") and "HANGUL" not in unicodedata.name(char, "")
        if wide and start is None:
            start = point
        if not wide and start is not None:
            ranges.append((start, point - 1))
            start = None
    return "".join("\\u{%X}" % a if a == b else "\\u{%X}-\\u{%X}" % (a, b) for a, b in ranges)


class WideTests(unittest.TestCase):
    def test_the_demos_table_is_the_services_rule(self):
        self.assertIn("const WIDE = /[%s]/u;" % wide_ranges(), BROWSER.read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("node"), "needs Node.js")
class WebFinishTests(unittest.TestCase):
    def test_the_demo_joins_a_continuation_as_the_service_does(self):
        ran = subprocess.run(["node", "-e", RUN, str(BROWSER), json.dumps(CASES)], capture_output=True, text=True,
                             timeout=10, check=True)
        self.assertEqual(json.loads(ran.stdout), [modes.finish("continue", text, output) for text, output in CASES])


if __name__ == "__main__":
    unittest.main()
