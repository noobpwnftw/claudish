"""Start the model and IME service together; Ctrl+C stops both."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from run_model import arguments, command

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from claudish import config
from claudish.model import Rewriter
from claudish.server import make_server


def local_rewriter(endpoint, profile=None):
    """The profile's context, bindings, modes, and prompt, with this script's model.

    Without --profile: "local" when the config file has it, else the file's default."""
    if profile is None and config.default_path().is_file():
        try:
            profiles = json.loads(config.default_path().read_text(encoding="utf-8")).get("profiles") or {}
        except (OSError, ValueError, AttributeError):
            profiles = {}  # resolve() below reports the real problem
        profile = "local" if "local" in profiles else None
    # Without a config file the built-in settings have no model: this script's is the local one.
    overrides = None if config.default_path().is_file() else {"backend": "llama"}
    name, settings, prompt, context = config.resolve(profile=profile, overrides=overrides)
    if settings["backend"] != "llama":
        raise ValueError("profile %r uses the %s backend; start.py runs the local model, so use "
                         "`python -m claudish serve --profile %s`" % (name, settings["backend"], name))
    settings["model_url"] = endpoint
    return Rewriter.from_settings(settings, prompt, context, name)


def bind_to_this_process(process):
    """Windows: put the model in a job object that is killed when this process ends, however it
    ends. `schtasks /end` (service uninstall) terminates start.py without running its cleanup,
    which left llama-server running, holding its port and locking its DLLs."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Limits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION; only LimitFlags is set
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD), ("IoCounters", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    limits = Limits(LimitFlags=0x2000)  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not (job and kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            and kernel32.AssignProcessToJobObject(job, int(process._handle))):
        print("warning: could not tie llama-server to this process (error %d)" % ctypes.get_last_error(), flush=True)
    return job  # the handle must stay open for the life of this process


def main():
    parser = argparse.ArgumentParser(description="Start Claudish and its local model")
    arguments(parser)
    parser.add_argument("--profile", help='Config profile for context, bindings, and modes (default: "local")')
    args = parser.parse_args()
    endpoint = "http://127.0.0.1:" + args.port
    try:
        cmd = command(args)
        rewriter = local_rewriter(endpoint, args.profile)
    except ValueError as exc:
        parser.error(str(exc))

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    # SIGTERM (kill, service managers) must stop the model too, not orphan it.
    signal.signal(signal.SIGTERM, interrupt)
    # Bind the service first, so port conflicts do not leave an orphan model.
    from claudish.client import write_token
    server = make_server(rewriter, token=write_token())
    process = None
    try:
        process = subprocess.Popen(cmd)
        job = bind_to_this_process(process)  # noqa: F841 (kept open until exit)
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                raise RuntimeError("llama-server exited during startup")
            try:
                with opener.open(endpoint + "/health", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("model did not become ready within 60 seconds")
            time.sleep(0.1)
        print("cd_AI ready. Browser demo: http://127.0.0.1:18765", flush=True)
        print("Ctrl+C stops the service and model.", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
