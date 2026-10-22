import json
from importlib.resources import files
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .composition import MAX_COMPOSITION


def make_server(rewriter, port=18765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log typed text.

        def reply(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_body(code, body, "application/json; charset=utf-8")

        def send_body(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; "
                             "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                             "base-uri 'none'; form-action 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def valid_host(self):
            return self.headers.get("Host") in (
                "127.0.0.1:%s" % self.server.server_port,
                "localhost:%s" % self.server.server_port,
            )

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {"error": "local host required"})
            if self.path == "/favicon.ico":
                return self.send_body(204, b"", "image/x-icon")
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/demo.css": ("demo.css", "text/css; charset=utf-8"),
                      "/demo.js": ("demo.js", "text/javascript; charset=utf-8"),
                      "/theme.js": ("theme.js", "text/javascript; charset=utf-8")}
            if self.path in assets:
                filename, content_type = assets[self.path]
                body = files("claudish").joinpath("web", filename).read_bytes()
                return self.send_body(200, body, content_type)
            if self.path == "/health":
                return self.reply(200, {"service": "cd_AI", "backend": rewriter.backend,
                                        "hosted": rewriter.hosted,
                                        "profile": getattr(rewriter, "profile", None),
                                        "modes": list(rewriter.modes),
                                        "timeout": rewriter.timeout})
            self.reply(404, {"error": "not found"})

        def do_POST(self):
            if not self.valid_host():
                return self.reply(403, {"error": "local host required"})
            if self.path != "/suggest":
                return self.reply(404, {"error": "not found"})
            # The local demo may call its own API; other websites may not.
            origin = self.headers.get("Origin")
            if origin is not None and origin != "http://" + self.headers["Host"]:
                return self.reply(403, {"error": "cross-origin requests are not accepted"})
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self.reply(403, {"error": "cross-site requests are not accepted"})
            if self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "application/json required"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 32768:
                    return self.reply(413, {"error": "invalid body size"})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("expected object")
                text = data.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_COMPOSITION:
                    raise ValueError("text must be 1–512 characters")
                # Optional text around the caret, supplied by an adapter.
                before, after = data.get("before", ""), data.get("after", "")
                if not all(isinstance(s, str) and len(s) <= 4000 for s in (before, after)):
                    raise ValueError("before/after must be strings of at most 4000 characters")
                mode = data.get("mode", "rewrite")
                app = data.get("app")  # The focused app, reported by the adapter; selects bindings.
                if app is not None and not (isinstance(app, str) and len(app) <= 200):
                    raise ValueError("app must be a short string")
                if mode not in rewriter.modes:
                    raise ValueError("unknown mode")
            except (ValueError, UnicodeError):
                return self.reply(400, {"error": "invalid text request"})
            try:
                result = rewriter.rewrite(text, before, after, mode, app)
            except Exception as exc:
                return self.reply(503, {"error": str(exc)})
            self.reply(200, result)

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def get_request(self):
            sock, address = super().get_request()
            sock.settimeout(5)
            return sock, address

    return Server(("127.0.0.1", port), Handler)
