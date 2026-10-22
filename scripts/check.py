"""Run the project's checks on this machine; the merge gate in place of remote CI.

python scripts/check.py            # unit tests, compile, diff, IBus and PIME smokes
python scripts/check.py --model    # also: real model, rewrite, fidelity eval, browser demo

Each check reports PASS, FAIL, or SKIP with a reason. Remote CI (push a ci/*
branch) is still the only Windows and macOS coverage; use it for adapter or
packaging changes.
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PIME_URL = ("https://raw.githubusercontent.com/EasyIME/PIME/e0ddf2ffc180837c2e9f8be363de4455c7532962/"
            "python/textService.py")
PIME_SHA256 = "c84fc2e9e79824d0d7692c895ba385287f6e29a3e5ba8cc25945b913694026ce"
results = []


def run(name, command, **options):
    started = time.monotonic()
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, **options)
    status = "PASS" if process.returncode == 0 else "FAIL"
    output = (process.stdout + process.stderr).strip().splitlines()
    results.append((name, status, "%.1fs" % (time.monotonic() - started)))
    if status == "FAIL":
        print("\n".join(output[-25:]))
    elif output:
        print("  " + output[-1])
    return process


def skip(name, reason):
    results.append((name, "SKIP", reason))


def pime_source():
    target = ROOT / ".tools/pime/textService.py"
    if not target.is_file():
        try:
            data = urlopen(PIME_URL, timeout=30).read()
        except OSError as exc:
            return None, "cannot download PIME textService.py: %s" % exc
        if hashlib.sha256(data).hexdigest() != PIME_SHA256:
            return None, "downloaded PIME textService.py does not match the pinned hash"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    elif hashlib.sha256(target.read_bytes()).hexdigest() != PIME_SHA256:
        return None, "%s does not match the pinned hash" % target
    return target, None


def port_free(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


def model_checks(args):
    if not (port_free(18765) and port_free(18766)):
        return skip("model", "ports 18765/18766 are in use; stop the running service first")
    log = tempfile.TemporaryFile()
    launcher = subprocess.Popen([sys.executable, "scripts/start.py", "--preset", args.preset],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 90
        while port_free(18765) or port_free(18766):
            if launcher.poll() is not None or time.monotonic() > deadline:
                log.seek(0)
                print(log.read().decode(errors="replace")[-2000:])
                return results.append(("model start", "FAIL", "launcher exited or timed out"))
            time.sleep(0.3)
        time.sleep(0.5)  # The service binds before the model reports ready.
        run("model rewrite", [sys.executable, "-m", "claudish", "rewrite", "This is very important."])
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "eval.json"
            if run("fidelity eval", [sys.executable, "benchmarks/evaluate.py", "--label", args.preset,
                                     "--output", str(report)]).returncode == 0:
                data = json.loads(report.read_text(encoding="utf-8"))
                results[-1] = ("fidelity eval", "PASS", "%d/%d pass checks, median %.0f ms" % (
                    data["faithful"], data["cases"], data["median_ms"]))
        browser = args.browser_python or ROOT / ".tools/browser-venv/bin/python"
        chromium = args.chromium or next(iter(sorted(glob.glob(os.path.expanduser(
            "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))), None)
        if not Path(browser).is_file():
            skip("browser demo", "no Playwright Python (pass --browser-python)")
        else:
            command = [str(browser), "tests/browser_demo.py"] + (["--executable", chromium] if chromium else [])
            run("browser demo", command, timeout=300)
    finally:
        launcher.terminate()
        try:
            launcher.wait(15)
        except subprocess.TimeoutExpired:
            launcher.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", action="store_true", help="Also run the real-model checks")
    parser.add_argument("--preset", choices=["tiny", "small"], default="small")
    parser.add_argument("--browser-python", help="Python with Playwright installed")
    parser.add_argument("--chromium", help="Chromium executable for Playwright")
    args = parser.parse_args()

    run("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    run("compileall", [sys.executable, "-m", "compileall", "-q", "claudish", "platforms", "scripts", "tests",
                       "benchmarks"])
    run("git diff --check", ["git", "diff", "--check", "HEAD"])
    system_python = Path("/usr/bin/python3")
    if not shutil.which("dbus-run-session") or not system_python.is_file():
        skip("IBus smoke", "needs dbus-run-session and /usr/bin/python3")
    elif subprocess.run([str(system_python), "-c", "import gi; gi.require_version('IBus', '1.0')"],
                        capture_output=True).returncode != 0:
        skip("IBus smoke", "system Python lacks PyGObject IBus bindings")
    else:
        run("IBus smoke", ["dbus-run-session", "--", str(system_python), "tests/ibus_smoke.py"])
    source, reason = pime_source()
    if source:
        run("PIME smoke", [sys.executable, "tests/pime_smoke.py", "--pime-source", str(source)])
    else:
        skip("PIME smoke", reason)
    if args.model:
        model_checks(args)

    print()
    for name, status, detail in results:
        print("%-16s %-4s  %s" % (name, status, detail))
    raise SystemExit(1 if any(status == "FAIL" for _, status, _ in results) else 0)


if __name__ == "__main__":
    main()
