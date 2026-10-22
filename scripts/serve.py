"""`claudish serve ARGS` from a checkout, wherever it is started from (service managers set no cwd)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claudish.__main__ import main  # noqa: E402

sys.argv = [sys.argv[0], "serve"] + sys.argv[1:]
main()
