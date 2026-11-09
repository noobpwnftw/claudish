import collections
import hmac
import json
import re
import sys
from pathlib import Path
from importlib.resources import files
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from .client import PORT
from .composition import AROUND, MAX_COMPOSITION


TEXTBOX_LIMIT = 200_000  # an instruction's text box, each side of the caret (the model sees a window)
BODY_LIMIT = 8 * TEXTBOX_LIMIT + 65536  # both sides, in UTF-8 and JSON escapes


TEXT_ERROR = "text must be 1–%d characters" % MAX_COMPOSITION


def checked_text(text):
    """What you typed: not blank, at most a composition's length."""
    if not (isinstance(text, str) and text.strip() and len(text) <= MAX_COMPOSITION):
        raise ValueError(TEXT_ERROR)
    return text


def checked_app(app):
    """The focused app as the adapter names it, or None."""
    if app is not None and not (isinstance(app, str) and len(app) <= 200):
        raise ValueError("app must be a short string")
    return app


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


def same(sent, known):
    """A token compared in constant time; one with characters a header should not have is wrong."""
    try:
        return hmac.compare_digest(sent, known)
    except TypeError:
        return False


def make_server(rewriter, port=PORT, token=None, reload=None, config_path=None):
    """token: what the input methods send (client.write_token() for a real service); a fresh one
    when None. Without it, a request is the demo's: text and a mode only, without the profile's
    context; sessions and their answers always need it. reload: builds the rewriter again from the
    config, after the settings window changed it (config_path, the file it reads)."""
    import secrets
    token = token or secrets.token_urlsafe(32)

    # The settings windows': a ticket (one use, a minute), then a token; the newest windows' only.
    tickets, settings_tokens = {}, collections.deque(maxlen=16)

    def swap():
        """The settings window's changes, from the next request on: every handler reads `rewriter`."""
        nonlocal rewriter
        from .model import warm_key
        read = stamp()  # before the files are read: an edit while the old model stops is still new
        fresh = reload()
        fresh.url = rewriter.url
        # What is running goes on: sessions, each text box's conversation, the recent requests.
        fresh.sessions, fresh.conversations, fresh.recent = rewriter.sessions, rewriter.conversations, rewriter.recent
        old = rewriter
        same = (old.warm and fresh.warm and type(old.warm) is type(fresh.warm)
                and warm_key(old.warm) == warm_key(fresh.warm)  # its kind, command, model and words
                and not old.warm.state.startswith("failed"))  # picked again after a failure: a new start
        fresh.adoptable = old.hand_over()  # routed profiles' model processes go on, for fresh to take up
        routed = fresh.adoptable.pop(warm_key(fresh.warm), None) if fresh.warm and not same else None
        if same:  # the same model process goes on (a tone or a binding changed)
            fresh.warm = old.warm  # and still old's for a request running there
            old.handed.append(old.warm)
        elif routed is not None:  # a profile it routed to is now the one in use: its process goes on
            fresh.warm = routed
        else:
            if old.warm:  # ended first: a local model's new server needs the port the old one has
                old.warm.stop()
            fresh.start_model()
        rewriter = fresh
        server.rewriter = fresh
        old.stop_model()
        # One nothing routes to any more (a binding or a mode's route removed): stopped now, not at
        # the next reload (a local model holds its memory meanwhile).
        # As route() goes: the service's bindings and its own modes, then a bound profile's modes.
        def modes_of(each):
            return {spec["profile"] for spec in each.modes.values() if spec.get("profile")}
        reachable, loaded = set(), {}

        def load(name):
            if name not in loaded:
                try:
                    loaded[name] = fresh.loader(name) if fresh.loader and name != fresh.profile else None
                except Exception:
                    loaded[name] = None
                if loaded[name] is not None and loaded[name].warm:
                    reachable.add(warm_key(loaded[name].warm))
            return loaded[name]
        for name in modes_of(fresh):
            load(name)
        for name in {b.profile for b in fresh.bindings if b.profile}:
            bound = load(name)
            for routed in modes_of(bound) if bound is not None else ():
                load(routed)
        for key in [key for key in fresh.adoptable if key not in reachable]:
            fresh.adoptable.pop(key).stop()
        stamps[0] = read

    def stamp():
        """When the config folder's JSON files (config.json, templates.json), its saved keys
        (`claudish key`), and the templates files its profiles name (in a folder of their own too)
        last changed."""
        path = config_path or _config_default()
        try:
            watched = set(path.parent.glob("*.json")) | set(path.parent.glob("*.key"))
        except OSError:
            return ()
        try:
            profiles = json.loads(path.read_text(encoding="utf-8-sig")).get("profiles") or {}
            watched.update(path.parent / Path(entry["templates"]).expanduser() for entry in profiles.values()
                           if isinstance(entry, dict) and isinstance(entry.get("templates"), str))
        except (OSError, ValueError, AttributeError, RuntimeError):  # RuntimeError: ~nobody/ in a path
            pass  # a config that does not read: its own file's change is enough
        found = []
        for each in watched:
            try:
                found.append((str(each), each.stat().st_mtime_ns))
            except (OSError, ValueError):  # ValueError: a NUL in a path
                pass
        return tuple(sorted(found))

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
            # errors="replace": text that is not Unicode (a lone surrogate) never drops the reply
            body = json.dumps(data, ensure_ascii=False).encode("utf-8", errors="replace")
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
            return same(self.headers.get("X-Claudish-Token") or "", token)

        def settings_trusted(self):
            """The settings page's token, or the service token."""
            sent = self.headers.get("X-Claudish-Settings") or ""
            return self.trusted() or any(same(sent, known) for known in list(settings_tokens))

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
            except (ValueError, UnicodeError, OSError, RecursionError):  # not JSON (or nested too deep), or a body shorter than it said
                data = None
            if not isinstance(data, dict):
                return self.reply(400, {"error": "expected a JSON object"})
            try:  # a lone surrogate ("\ud800") is valid JSON but not text: refused before it is kept
                json.dumps(data, ensure_ascii=False).encode("utf-8")
            except UnicodeEncodeError:
                return self.reply(400, {"error": "the text is not valid Unicode (half an emoji?)"})
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
                try:
                    checked_text(text), checked_app(app)
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
                if conversation is not None and not (isinstance(conversation, str) and 0 < len(conversation) <= 64):
                    return self.reply(400, {"error": "conversation must be a short id"})
                if not (isinstance(before, str) and isinstance(after, str) and len(before) <= TEXTBOX_LIMIT and len(after) <= TEXTBOX_LIMIT):
                    return self.reply(400, {"error": "before/after must be strings of at most %d characters"
                                                     % TEXTBOX_LIMIT})
                if not isinstance(look, bool):
                    return self.reply(400, {"error": "look is a boolean"})
                draft = data.get("draft") or None
                if draft is not None and not (isinstance(draft, str) and len(draft) <= TEXTBOX_LIMIT):
                    return self.reply(400, {"error": "draft is the draft in view, a string"})
                try:
                    purpose = checked_purpose(data.get("purpose"))
                    session = rewriter.route(app, "instruct").start_session(text, app, conversation, before, after,
                                                                            look, purpose, draft=draft)
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
                except Exception as exc:  # the profile it routes to cannot run (its SDK missing): said, not a dropped reply
                    return self.reply(503, {"error": str(exc) or type(exc).__name__})
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
                session.cancel(keep=data.get("keep") is True)
                return self.reply(200, {"ok": True})
            if parts[2] != "answer":
                return self.reply(404, {"error": "not found"})
            choice, text = data.get("choice"), data.get("text")
            if not isinstance(data.get("question"), str):
                return self.reply(400, {"error": "question must be a question's id"})
            if text is not None and not (isinstance(text, str) and 0 < len(text) <= MAX_COMPOSITION):
                return self.reply(400, {"error": TEXT_ERROR})
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
            if conversation is None or not same(token, conversation.token):
                return self.reply(404, {"error": "no such conversation"})
            try:
                if data.get("op") == "read":
                    text = conversation.textbox.read(data.get("start", 0), data.get("length", 2000))
                elif data.get("op") == "search":
                    text = conversation.textbox.search(data.get("query", ""))
                else:
                    return self.reply(400, {"error": "op is read or search"})
            except (TypeError, ValueError, OverflowError) as exc:  # Infinity as an offset
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
            events, done = session.wait(int(after) if re.fullmatch("[0-9]{1,9}", after) else 0, timeout=1.0)
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
            page = self.path.split("?", 1)[0]  # the lab takes its state from the query (design.js)
            if page in assets:
                filename, content_type = assets[page]
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
                try:  # two readers at once may both drop the oldest
                    while clock.time() - rewriter.recent[0]["time"] > RECENT_SECONDS:
                        rewriter.recent.popleft()
                except IndexError:
                    pass
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
                    **({"problem": rewriter.problem} if rewriter.problem else {}),
                    **({"unavailable": rewriter.unavailable} if rewriter.unavailable else {}),
                    # Whether this service has a Claude key: a terminal's variable may not reach it.
                    **({"key": bool(rewriter.claude.credential)} if rewriter.claude else {}),
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
                # The folder's config files as they were (a first save writes templates.json too).
                before = {each: each.read_bytes() for each in path.parent.glob("*.json*") if each.is_file()}
                # And the keys it may save (the Keychain on macOS): put back with the files.
                from . import keys
                api = data.get("server") if isinstance(data.get("server"), dict) else {}
                names = (["anthropic"] if data.get("key") else []) + \
                    ([keys.server_name(api["url"])] if api.get("key") and isinstance(api.get("url"), str) else [])
                saved = {name: keys.stored(name) for name in names}

                def put_back():
                    for each in path.parent.glob("*.json*"):
                        if each not in before:
                            each.unlink(missing_ok=True)
                    for each, content in before.items():
                        each.write_bytes(content)
                    for name, key in saved.items():
                        keys.store(key, name) if key else keys.forget(name)
                    stamps[0] = stamp()  # put back as the service runs it: nothing to take up
                try:
                    shown = settings.apply(data, config_path)
                except ValueError as exc:
                    return self.reply(400, {"error": str(exc)})
                except Exception as exc:  # the keychain, the disk: said on the page, not a dropped connection
                    try:  # a key saved before the step that failed goes back with the files
                        put_back()
                    except Exception:
                        pass
                    return self.reply(500, {"error": "cd_AI could not save that (%s)" % (exc,)})
                if reload is not None:
                    try:
                        swap()
                    except Exception as exc:  # it would not start at the next login either: put it back
                        put_back()
                        return self.reply(400, {"error": "cd_AI could not use that, so nothing changed (%s)" % exc})
                    if "choice" in data and server.rewriter.profile != shown["profile"]:
                        # Started with a profile of its own (--profile, the local model's service): it
                        # does not follow the file's, so the choice would be shown and never used.
                        put_back()
                        swap()
                        return self.reply(400, {"error": "this service runs the %r profile it was started with, so "
                                                         "nothing changed: `claudish service install` runs it with "
                                                         "the config's profile" % server.rewriter.profile})
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
            settings_tokens.append(session)
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
                text = checked_text(data.get("text"))
                # Optional text around the caret, supplied by an adapter.
                before, after = data.get("before", ""), data.get("after", "")
                if not all(isinstance(s, str) and len(s) <= AROUND for s in (before, after)):
                    raise ValueError("before/after must be strings of at most %d characters" % AROUND)
                mode = data.get("mode", "rewrite")
                app = checked_app(data.get("app"))  # The focused app, reported by the adapter; selects bindings.
                if not isinstance(mode, str) or mode not in rewriter.modes:
                    raise ValueError("unknown mode")
                look = data.get("look", False)  # F8: the user asked for a picture of the focused window
                if not isinstance(look, bool) or (look and mode != "instruct"):
                    raise ValueError("look is a boolean, for instruct only")
                purpose = checked_purpose(data.get("purpose"))
                again = data.get("again", True)  # false: a measurement's repeat, not another take
                draft = data.get("draft") or ""  # a follow-up's draft in view (the web demo's)
                if not (isinstance(draft, str) and len(draft) <= AROUND) or (draft and mode != "instruct"):
                    raise ValueError("draft is the draft in view, for instruct only")
                if not isinstance(again, bool):
                    raise ValueError("again is a boolean")
            except (ValueError, UnicodeError) as exc:
                return self.reply(400, {"error": str(exc)})
            trusted = self.trusted()
            if not trusted and (app or look or before or after or purpose):
                # What is around the caret, the app (which can mean reading a terminal) and window
                # pictures come only from an input method.
                return self.reply(403, {"error": "the service token is required"})
            try:
                if mode == "continue" and not (rewriter.continues(app) if trusted else rewriter.autocompletes):
                    # Autocomplete runs at every pause: a hosted model only where a profile routes it.
                    return self.reply(503, {"error": "continue has no model of its own"})
                answerer = rewriter.route(app, mode) if trusted else rewriter  # which AI answers here
                result = answerer.rewrite(text, before, after, mode, app, look, purpose, context=trusted, again=again,
                                          draft=draft)
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
