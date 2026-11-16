"""Processes cd_AI starts (llama-server, a warm Claude Code or Codex, agent sessions, commands,
context commands, MCP servers, terminals): tied to the service where they end with it (spawn),
their environment (environment, session_display), ended with a .cmd shim's CLI (kill), and the
end of what they said (tail)."""
import os
import platform
import subprocess
import threading

JOB = []  # Windows: the one job object every child is put in, made at the first
LOCK = threading.Lock()


KERNEL32 = []  # Windows: cd_AI's own kernel32, its functions declared once (windows())


def windows():
    """kernel32 with the functions used here declared (a WinDLL of its own: ctypes.windll's is
    shared with the rest of the process)."""
    import ctypes
    from ctypes import wintypes
    with LOCK:
        if not KERNEL32:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
            kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
            kernel32.Process32FirstW.argtypes = kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            KERNEL32.append(kernel32)
    return KERNEL32[0]


def bind_to_this_process(process, what="the model"):
    """Windows: put the process in the service's job object, which is killed when this process ends,
    however it ends (one for every child: a handle per child would add up, a process per request). `schtasks /end` (service uninstall) terminates the service without running its cleanup,
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

    kernel32 = windows()
    with LOCK:
        if not JOB:
            job = kernel32.CreateJobObjectW(None, None)
            limits = Limits(LimitFlags=0x2000)  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if job and kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                JOB.append(job)
    job = JOB[0] if JOB else None
    if not (job and kernel32.AssignProcessToJobObject(job, int(process._handle))):
        print("warning: could not tie %s to this process (error %d)" % (what, ctypes.get_last_error()), flush=True)
    return job  # the handle stays open for the life of this process (JOB)


NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: the service has no console to share
OWN_ENV = set()  # variables set for cd_AI's own process, not for the programs it starts (platforms/macos/main.py)


def environment(program=None):
    """The environment for a program cd_AI starts: without OWN_ENV, and with the program's folder
    first on PATH (an npm install's claude, codex or npx is a node script, and its node is beside
    it: Homebrew's bin, an nvm version's bin), which a login service's PATH lacks."""
    env = {key: value for key, value in os.environ.items() if key not in OWN_ENV}
    folder = os.path.dirname(os.path.expanduser(program or ""))
    path = env.get("PATH", "")
    if folder and folder not in path.split(os.pathsep):
        env["PATH"] = folder + os.pathsep + path if path else folder
    return env


SESSION_DISPLAY = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY")


def session_display():
    """The desktop session's display, for a window picture or a terminal window: the systemd user
    service starts at login, before the desktop gives the user manager DISPLAY and WAYLAND_DISPLAY,
    so it has none of its own. Taken from the user manager as it is now, where this service lacks
    them (Linux under systemd only)."""
    if platform.system() != "Linux" or not os.environ.get("INVOCATION_ID") or all(
            os.environ.get(name) for name in SESSION_DISPLAY[:2]):
        return
    try:
        shown = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return
    for line in shown.stdout.splitlines():
        name, _, value = line.partition("=")
        if name in SESSION_DISPLAY and value and not os.environ.get(name):
            os.environ[name] = value


def spawn(argv, what, job=True, **options):
    """A child process tied to this one: a Windows job object, and on every platform its stdin,
    which closes when the service goes (both CLIs end at the end of their input). Not Linux's
    parent-death signal: it fires when the starting thread ends, and warm-ups start on a thread.
    job=False: its stdin only, so what it starts for you (an agent's programs) outlives the service,
    as on Linux and macOS (the job kills every process in it)."""
    if os.name == "nt":
        options.setdefault("creationflags", NO_WINDOW)
    process = subprocess.Popen(argv, **options)
    process.claudish_job = bind_to_this_process(process, what) if job else None
    return process


def kill(process):
    """A child ended now. On Windows a .cmd or .bat (an npm install's claude.cmd, codex.cmd) runs in
    cmd.exe, and the CLI is its child: killing cmd.exe alone leaves the CLI answering, holding the
    output pipe. Its direct children go too; what those started stays, as on Linux and macOS."""
    shim = os.name == "nt" and str(process.args[0] if isinstance(process.args, (list, tuple)) else process.args
                                   ).lower().endswith((".cmd", ".bat"))
    kids = children_of(process.pid) if shim and process.poll() is None else []
    try:
        process.kill()
    except OSError:
        pass  # it ended meanwhile
    for pid in kids:
        terminate(pid)


def children_of(pid):
    """Windows: the process ids whose parent is pid (a snapshot of the process list)."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    kernel32 = windows()
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return []
    found = []
    try:
        entry = Entry(dwSize=ctypes.sizeof(Entry))
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32ParentProcessID == pid:
                found.append(entry.th32ProcessID)
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def terminate(pid):
    """Windows: the process pid, ended."""
    kernel32 = windows()
    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if handle:
        kernel32.TerminateProcess(handle, 1)
        kernel32.CloseHandle(handle)


def tail(stream, keep):
    """A child's stderr read on a thread into keep (a bounded deque); the thread, to wait for its end."""
    def read():
        try:
            keep.extend(stream)
        except (OSError, ValueError):
            pass  # closed under it: the process was killed
        finally:
            stream.close()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    return reader
