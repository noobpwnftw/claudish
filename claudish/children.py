"""Model processes the service runs (llama-server, a warm Claude Code or Codex): started tied to the
service, so they end when it ends, however it ends."""
import os
import subprocess


def bind_to_this_process(process, what="the model"):
    """Windows: put the process in a job object that is killed when this process ends, however it
    ends. `schtasks /end` (service uninstall) terminates the service without running its cleanup,
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
        print("warning: could not tie %s to this process (error %d)" % (what, ctypes.get_last_error()), flush=True)
    return job  # the handle must stay open for the life of this process


def spawn(argv, what, **options):
    """A child process tied to this one: a Windows job object, and on every platform its stdin,
    which closes when the service goes (both CLIs end at the end of their input). Not Linux's
    parent-death signal: it fires when the starting thread ends, and warm-ups start on a thread."""
    if os.name == "nt":
        options.setdefault("creationflags", 0x08000000)  # CREATE_NO_WINDOW
    process = subprocess.Popen(argv, **options)
    process.claudish_job = bind_to_this_process(process, what)
    return process
