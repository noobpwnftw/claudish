import hmac
import json
import sys
from importlib.resources import files
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from .composition import MAX_COMPOSITION


TEXTBOX_LIMIT = 200_000  # an instruction's text box, each side of the caret (the model sees a window)
BODY_LIMIT = 8 * TEXTBOX_LIMIT + 65536  # both sides, in UTF-8 and JSON escapes


def checked_purpose(purpose):
    """The field's kind as the input method reports it ("terminal", "email", ...), or None."""
    if purpose is not None and not (isinstance(purpose, str) and purpose.isidentifier() and len(purpose) <= 32):
        raise ValueError("purpose must be a short name")
    if purpose in ("password", "pin"):
        raise ValueError("not for this field")
    return purpose


def _config_default():
    from .config import default_path
    return default_path()


def make_server(rewriter, port=18765, token=None, reload=None, config_path=None):
    """token: what the input methods send (client.write_token() for a real service); a fresh one
    when None. Without it, a request is the demo's: text and a mode only, without the profile's
    context; sessions and their answers always need it. reload: builds the rewriter again from the
    config, after the settings window changed it (config_path, the file it reads)."""
    import secrets
    token = token or secrets.token_urlsafe(32)

    tickets, settings_tokens = {}, set()  # the settings window's: a ticket (one use, a minute), then a token

    def swap():
        """The settings window's changes, from the next request on: every handler reads `rewriter`."""
        nonlocal rewriter
        fresh = reload()
        fresh.url = rewriter.url
        # What is running goes on: sessions, each text box's conversation, the recent requests.
        fresh.sessions, fresh.conversations, fresh.recent = rewriter.sessions, rewriter.conversations, rewriter.recent
        old = rewriter
        same = (old.warm and fresh.warm and type(old.warm) is type(fresh.warm)
                and (old.warm.command, old.warm.model) == (fresh.warm.command, fresh.warm.model))
        if same:  # the same model process goes on (a tone or a binding changed)
            fresh.warm, old.warm = old.warm, None
        else:
            fresh.start_model()
        rewriter = fresh
        server.rewriter = fresh
        old.stop_model()
        stamps[0] = stamp()

    def stamp():
        """When the config folder's JSON files (config.json, templates.json) last changed."""
        folder = (config_path or _config_default()).parent
        try:
            return tuple(sorted((path.name, path.stat().st_mtime_ns) for path in folder.glob("*.json")))
        except OSError:
            return ()

    stamps = [stamp()]
    import threading
    rebuilding = threading.Lock()

    def edited():
        """A hand edit of config.json or a templates file: taken up at the next request. One that
        does not build leaves the service as it was, and says why."""
        if reload is None or stamp() == stamps[0]:
            return
        with rebuilding:
            if stamp() == stamps[0]:
                return  # another request took it up
            stamps[0] = stamp()
            try:
                swap()
                print("Took up the edited config.", flush=True)
            except Exception as exc:
                print("The edited config was not taken up: %s" % (exc,), file=sys.stderr, flush=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

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

        def trusted(self):
            """Sent by an input method."""
            return hmac.compare_digest(self.headers.get("X-Claudish-Token") or "", token)

        def settings_trusted(self):
            """The settings page's token, or the service token."""
            sent = self.headers.get("X-Claudish-Settings") or ""
            return self.trusted() or any(hmac.compare_digest(sent, known) for known in list(settings_tokens))

        def valid_host(self):
            return self.headers.get("Host") in (
                "127.0.0.1:%s" % self.server.server_port,
                "localhost:%s" % self.server.server_port,
            )

        def json_request(self, limit=32768):
            """The checked JSON body of a request from this machine's own pages, or None after replying."""
            origin = self.headers.get("Origin")
            if origin is not None and origin != "http://" + self.headers["Host"]:
                return self.reply(403, {"error": "cross-origin requests are not accepted"})
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self.reply(403, {"error": "cross-site requests are not accepted"})
            if self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "application/json required"})
            try:
                size = int(self.headers.get("Content-Length", "0") or 0)
            except ValueError:
                size = 0
            if not 0 < size <= limit:
                return self.reply(413, {"error": "invalid body size"})
            try:
                data = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeError):
                data = None
            if not isinstance(data, dict):
                return self.reply(400, {"error": "expected a JSON object"})
            return data

        def post_session(self):
            """POST /sessions {text, app?}; /sessions/ID/answer {question, choice | text}; /sessions/ID/cancel."""
            parts = self.path.strip("/").split("/")
            if not self.trusted() and not (len(parts) == 3 and parts[0] == "conversations" and parts[2] == "textbox"):
                return self.reply(403, {"error": "the service token is required"})
            data = self.json_request(BODY_LIMIT if parts == ["sessions"] else 32768)
            if data is None:
                return
            if parts == ["sessions"]:
                text, app = data.get("text"), data.get("app")
                conversation, look = data.get("conversation"), data.get("look", False)
                before, after = data.get("before", ""), data.get("after", "")
                if not (isinstance(text, str) and text.strip() and len(text) <= MAX_COMPOSITION):
                    return self.reply(400, {"error": "text must be 1–512 characters"})
                if app is not None and not (isinstance(app, str) and len(app) <= 200):
                    return self.reply(400, {"error": "app must be a short string"})
                if conversation is not None and not (isinstance(conversation, str) and 0 < len(conversation) <= 64):
                    return self.reply(400, {"error": "conversation must be a short id"})
                if not (isinstance(before, str) and isinstance(after, str) and len(before) <= TEXTBOX_LIMIT and len(after) <= TEXTBOX_LIMIT):
                    return self.reply(400, {"error": "before/after must be strings of at most %d characters"
                                                     % TEXTBOX_LIMIT})
                if not isinstance(look, bool):
                    return self.reply(400, {"error": "look is a boolean"})
                try:
                    purpose = checked_purpose(data.get("purpose"))
                    session = rewriter.route(app, "instruct").start_session(text, app, conversation, before, after,
                                                                            look, purpose)
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
                except RuntimeError as exc:
                    return self.reply(503, {"error": str(exc)})
                return self.reply(200, {"id": session.id})
            if len(parts) == 3 and parts[0] == "conversations" and parts[2] == "textbox":
                return self.textbox(parts[1], data)
            if parts == ["recent", "clear"]:
                rewriter.recent.clear()
                return self.reply(200, {"ok": True})
            if len(parts) == 3 and parts[0] == "conversations" and parts[2] == "end":
                rewriter.conversations.end(parts[1])  # its text box went away
                return self.reply(200, {"ok": True})
            session = rewriter.sessions.get(parts[1]) if len(parts) == 3 else None
            if session is None:
                return self.reply(404, {"error": "no such session"})
            if parts[2] == "cancel":
                session.cancel()
                return self.reply(200, {"ok": True})
            if parts[2] != "answer":
                return self.reply(404, {"error": "not found"})
            choice, text = data.get("choice"), data.get("text")
            if text is not None and not (isinstance(text, str) and 0 < len(text) <= MAX_COMPOSITION):
                return self.reply(400, {"error": "text must be 1–512 characters"})
            try:
                session.answer(data.get("question"), None if text is not None else choice, text)
            except ValueError as exc:
                return self.reply(400, {"error": str(exc)})
            return self.reply(200, {"ok": True})

        def textbox(self, key, data):
            """POST /conversations/ID/textbox {op: read|search, ...}: the conversation's text box, for
            its agent (claudish textbox-mcp). With the conversation's token."""
            conversation = rewriter.conversations.find(key)
            token = self.headers.get("X-Claudish-Token") or ""
            if conversation is None or not hmac.compare_digest(token, conversation.token):
                return self.reply(404, {"error": "no such conversation"})
            try:
                if data.get("op") == "read":
                    text = conversation.textbox.read(data.get("start", 0), data.get("length", 2000))
                elif data.get("op") == "search":
                    text = conversation.textbox.search(data.get("query", ""))
                else:
                    return self.reply(400, {"error": "op is read or search"})
            except (TypeError, ValueError) as exc:
                return self.reply(400, {"error": str(exc)})
            return self.reply(200, {"text": text})

        def get_session(self):
            """GET /sessions/ID?after=N: new events, waiting up to a second for the first."""
            if not self.trusted():
                return self.reply(403, {"error": "the service token is required"})
            path, _, query = self.path.partition("?")
            session = rewriter.sessions.get(path[len("/sessions/"):])
            if session is None:
                return self.reply(404, {"error": "no such session"})
            after = query[len("after="):] if query.startswith("after=") else "0"
            events, done = session.wait(int(after) if after.isdigit() else 0, timeout=1.0)
            return self.reply(200, {"events": events, "done": done})

        def do_GET(self):
            edited()
            if not self.valid_host():
                return self.reply(403, {"error": "local host required"})
            if self.path in ("/favicon.ico", "/favicon.png"):
                return self.send_body(200, files("claudish").joinpath("web", "favicon.png").read_bytes(), "image/png")
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/demo.css": ("demo.css", "text/css; charset=utf-8"),
                      "/demo.js": ("demo.js", "text/javascript; charset=utf-8"),
                      "/theme.js": ("theme.js", "text/javascript; charset=utf-8"),
                      "/kit.css": ("kit.css", "text/css; charset=utf-8"),
                      "/kit.js": ("kit.js", "text/javascript; charset=utf-8"),
                      "/ai-tile.png": ("ai-tile.png", "image/png"),
                      "/design.html": ("design.html", "text/html; charset=utf-8"),
                      "/design.css": ("design.css", "text/css; charset=utf-8"),
                      "/design.js": ("design.js", "text/javascript; charset=utf-8"),
                      "/lab-states.js": ("lab-states.js", "text/javascript; charset=utf-8"),
                      "/settings": ("settings.html", "text/html; charset=utf-8"),
                      "/settings.css": ("settings.css", "text/css; charset=utf-8"),
                      "/settings.js": ("settings.js", "text/javascript; charset=utf-8")}
            if self.path in assets:
                filename, content_type = assets[self.path]
                body = files("claudish").joinpath("web", filename).read_bytes()
                return self.send_body(200, body, content_type)
            if self.path.startswith("/sessions/"):
                return self.get_session()
            if self.path == "/settings/state":
                if not self.settings_trusted():
                    return self.reply(403, {"error": "the service token is required"})
                from . import settings
                try:
                    shown = settings.state(config_path)
                except (OSError, ValueError) as exc:  # a config file that does not read: say which
                    return self.reply(500, {"error": "cd_AI could not read its config (%s)" % (exc,)})
                return self.reply(200, dict(shown, service=self.health()))
            if self.path == "/recent":
                if not self.trusted():
                    return self.reply(403, {"error": "the service token is required"})
                from .model import RECENT_SECONDS
                import time as clock
                while rewriter.recent and clock.time() - rewriter.recent[0]["time"] > RECENT_SECONDS:
                    rewriter.recent.popleft()
                return self.reply(200, {"recent": list(rewriter.recent)})
            if self.path == "/health":
                return self.reply(200, self.health())
            self.reply(404, {"error": "not found"})

        def health(self):
            return {"service": "cd_AI", "backend": rewriter.backend,
                    "profile": rewriter.profile,
                    # Which app goes to which profile (the AI that answers there).
                    "routes": {b.pattern: b.profile for b in rewriter.bindings if b.profile},
                    "modes": list(rewriter.modes), "timeout": rewriter.timeout,
                    "keys": {"summon": rewriter.summon},
                    "hints": rewriter.hints,
                    **({"model": rewriter.model_state} if rewriter.model_state else {})}

        def post_settings(self):
            """The settings window: its changes go to the config (the key to its store), and the
            service takes them up at once."""
            if not self.settings_trusted():
                return self.reply(403, {"error": "the service token is required"})
            data = self.json_request()
            if data is None:
                return None
            from . import settings
            path = config_path or settings.config.default_path()
            # A model/key check can be slow. Keep another window's save (and hand-edit reloads)
            # out of its read/modify/write and rollback, so accepted changes are not lost.
            with rebuilding:
                before = path.read_bytes() if path.is_file() else None
                try:
                    shown = settings.apply(data, config_path)
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
                except Exception as exc:  # the keychain, the disk: said on the page, not a dropped connection
                    return self.reply(500, {"error": "cd_AI could not save that (%s)" % (exc,)})
                if reload is not None:
                    try:
                        swap()
                    except Exception as exc:  # it would not start at the next login either: put it back
                        if before is None:
                            path.unlink(missing_ok=True)
                        else:
                            path.write_bytes(before)
                        stamps[0] = stamp()  # put back as the service runs it: nothing to take up
                        return self.reply(400, {"error": "cd_AI could not use that, so nothing changed (%s)" % exc})
                return self.reply(200, dict(shown, service=self.health()))

        def post_ticket(self):
            """`claudish settings` asks for a ticket to put in the page's
            address; the page trades it, once and within a minute, for a token for settings only."""
            import time as clock
            if self.path == "/settings/ticket":
                if not self.trusted():
                    return self.reply(403, {"error": "the service token is required"})
                for old in [t for t, expires in tickets.items() if expires < clock.monotonic()]:
                    tickets.pop(old, None)
                ticket = secrets.token_urlsafe(24)
                tickets[ticket] = clock.monotonic() + 60
                return self.reply(200, {"ticket": ticket})
            data = self.json_request(limit=1024)
            if data is None:
                return None
            expires = tickets.pop(data.get("ticket") if isinstance(data.get("ticket"), str) else "", 0)
            if expires < clock.monotonic():
                return self.reply(403, {"error": "this settings link has expired: open settings again"})
            session = secrets.token_urlsafe(32)
            settings_tokens.add(session)
            return self.reply(200, {"token": session})

        def do_POST(self):
            edited()
            if not self.valid_host():
                return self.reply(403, {"error": "local host required"})
            if self.path.startswith(("/sessions", "/conversations/", "/recent/")):
                return self.post_session()
            if self.path == "/settings":
                return self.post_settings()
            if self.path in ("/settings/ticket", "/settings/session"):
                return self.post_ticket()
            if self.path != "/suggest":
                return self.reply(404, {"error": "not found"})
            data = self.json_request()
            if data is None:
                return
            try:
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
                look = data.get("look", False)  # F8: the user asked for a picture of the focused window
                if not isinstance(look, bool) or (look and mode != "instruct"):
                    raise ValueError("look is a boolean, for instruct only")
                purpose = checked_purpose(data.get("purpose"))
            except (ValueError, UnicodeError) as exc:
                return self.reply(400, {"error": str(exc)})
            trusted = self.trusted()
            if not trusted and (app or look or before or after or purpose):
                # What is around the caret, the app (which can mean reading a terminal) and window
                # pictures come only from an input method.
                return self.reply(403, {"error": "the service token is required"})
            if mode == "continue" and not (rewriter.continues(app) if trusted else rewriter.autocompletes):
                # Autocomplete runs at every pause: a hosted model only where a profile routes it.
                return self.reply(503, {"error": "continue has no model of its own"})
            try:
                answerer = rewriter.route(app, mode) if trusted else rewriter  # which AI answers here
                result = answerer.rewrite(text, before, after, mode, app, look, purpose, context=trusted)
            except Exception as exc:
                from .composition import failure
                return self.reply(503, {"error": str(exc), "said": failure(exc)})  # said: in the panel's words
            self.reply(200, result)

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        # On Windows SO_REUSEADDR lets a second process bind a port already in use (on Linux and macOS
        # it only reuses one in TIME_WAIT): a second `serve` would start beside the first and replace
        # its token. Without it, the second one finds the port taken and leaves.
        allow_reuse_address = sys.platform != "win32"

        def server_bind(self):
            # HTTPServer looks up the host's name (socket.getfqdn), a reverse lookup that on macOS
            # can go out over multicast DNS and raise a macOS prompt. Loopback
            # needs no name.
            TCPServer.server_bind(self)
            self.server_name, self.server_port = "localhost", self.server_address[1]

        def get_request(self):
            sock, address = super().get_request()
            sock.settimeout(5)
            return sock, address

    server = Server(("127.0.0.1", port), Handler)
    server.token = token
    server.rewriter = rewriter
    rewriter.url = "http://127.0.0.1:%d" % server.server_port  # for the agents' textbox MCP server
    return server
