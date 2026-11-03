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
const finish = new Function(src.slice(src.indexOf("function finish"), src.indexOf("\\n}\\n", src.indexOf("function finish")) + 3)
                            + "; return finish;")();
console.log(JSON.stringify(JSON.parse(process.argv[2]).map(([text, output]) => finish("continue", text, output))));
"""
CASES = [["I ", "in fact, we are thrilled."], ["A ", "As a team, we ship."], ['She said "we are ', 'ready to launch."'],
         ["Dear Sam,", '"I hope this finds you well."'], ["hello ", "Hello, how are you today?"],
         ["Thanks for", "Thanks for the review."], ["我今天", "去了商店。"], ["It works", "—mostly."], ["Thanks", "  "],
         ["Shipped it 🎉", "See you tomorrow."], ["Great", "👍 thanks"], ["ｱｲｳ", "test"], ["ok", "ﾃｽﾄ"], ["안녕하세요", "반갑습니다."]]


@unittest.skipUnless(shutil.which("node"), "needs Node.js")
class WebFinishTests(unittest.TestCase):
    def test_the_demo_joins_a_continuation_as_the_service_does(self):
        ran = subprocess.run(["node", "-e", RUN, str(BROWSER), json.dumps(CASES)], capture_output=True, text=True,
                             timeout=10, check=True)
        self.assertEqual(json.loads(ran.stdout), [modes.finish("continue", text, output) for text, output in CASES])


if __name__ == "__main__":
    unittest.main()
