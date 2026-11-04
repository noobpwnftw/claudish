"""Shared test helpers: a service on a free port, waiting for a worker's result, and for a
session's question."""
import threading
import time
from contextlib import contextmanager

from claudish.server import make_server


@contextmanager
def serving(rewriter, **settings):
    """The service on a free port for the block, then shut down."""
    server = make_server(rewriter, 0, **settings)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def poll_until(worker, timeout=1):
    """The worker's next result, or None after timeout seconds."""
    deadline = time.monotonic() + timeout
    result = None
    while result is None and time.monotonic() < deadline:
        result = worker.poll()
        time.sleep(0.001)
    return result


def asked(session, timeout=5):
    """The session's first question event, once it is there (None after timeout seconds)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not any(e["type"] == "question" for e in session.events):
        time.sleep(0.01)
    return next((e for e in session.events if e["type"] == "question"), None)
