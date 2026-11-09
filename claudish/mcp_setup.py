"""MCP onboarding: import servers already set up for Claude, list their tools, and test context per app.

claudish mcp import [--dry-run] [--replace]   copy servers from Claude Desktop / Claude Code into the config
claudish mcp list                             connect to each configured server; show its tools and resources
claudish context test --app NAME              which bindings match NAME, and what each provider returns
Env and header values become "$NAME" references to your environment.
"""
import json
import os
import platform
import re
from pathlib import Path

from . import config
from .context import variables


def claude_sources():
    """[(label, path)] of Claude configs that may define MCP servers: the ones you set up yourself. A
    project's .mcp.json stays with its project (Claude Code runs it there, once trusted), not in
    cd_AI's config."""
    home = Path.home()
    system = platform.system()
    desktop = (Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Claude" if system == "Windows"
               else home / "Library/Application Support/Claude" if system == "Darwin"
               else Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "Claude")
    return [("Claude Desktop", desktop / "claude_desktop_config.json"),
            ("Claude Code (user)", home / ".claude.json")]


def discover(skipped=None):
    """{name: (where, server)}: the servers you set up for Claude: Claude Desktop's, Claude Code's for
    you (user scope) and the ones `claude mcp add` keeps per project (local scope, its default).
    skipped gets (name, where, why) for one turned off there or already found elsewhere."""
    found, skipped = {}, skipped if skipped is not None else []
    for label, path in claude_sources():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        groups = [(label, data.get("mcpServers"), ())]
        for project, settings in sorted((data.get("projects") or {}).items()):
            if isinstance(settings, dict):
                groups.append(("%s, project %s" % (label, project), settings.get("mcpServers"),
                               settings.get("disabledMcpServers") or ()))
        for where, servers, disabled in groups:
            for name, server in (servers or {}).items() if isinstance(servers, dict) else ():
                if not isinstance(server, dict):
                    continue
                if server.get("disabled") is True or name in disabled:
                    skipped.append((name, where, "turned off there"))
                elif name in found:
                    skipped.append((name, where, "the one from %s is used" % found[name][0]))
                else:
                    found[name] = (where, server)
    return found


def variable(*parts):
    return re.sub(r"[^A-Z0-9]+", "_", "_".join(parts).upper()).strip("_")


def sanitize(name, server):
    """(server for our config, [environment variables to set])."""
    needed, clean = [], {}
    if server.get("url"):
        clean["url"] = server["url"]
        clean["type"] = "sse" if server.get("type") == "sse" else "http"  # Claude Code needs it said
        needed += variables(server["url"])
        headers = {}
        for key, value in (server.get("headers") or {}).items():
            if variables(str(value)):  # "Bearer ${TOKEN}", "${TOKEN:-dev}": kept as written
                headers[key] = str(value)
                needed += variables(str(value))
            else:
                var = variable("CLAUDISH_MCP", name, key)
                headers[key] = "$" + var
                needed.append(var)
        if headers:
            clean["headers"] = headers
    else:
        clean["command"] = server.get("command")
        clean["args"] = list(server.get("args") or [])
        env = {}
        for key, value in (server.get("env") or {}).items():
            if variables(str(value)):  # "$TOKEN", "${PATH_TO:-~/notes}": kept as written
                env[key] = str(value)
                needed += variables(str(value))
            else:  # a value written there: from your environment here, not copied into the config
                env[key] = "$" + key
                needed.append(key)
        if env:
            clean["env"] = env
    return clean, needed


def read_config(path):
    """The config file's data; {} when there is none. ValueError when it does not read."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict) or not isinstance(data.get("mcp_servers", {}), dict):
        raise ValueError("cannot read %s: not a cd_AI config (an object with \"mcp_servers\")" % path)
    return data


def import_servers(path=None, dry_run=False, replace=False):
    from .service import as_typed
    path = Path(path or config.default_path())
    data = read_config(path) if path.exists() else json.loads(json.dumps(config.STARTER))
    servers = data.setdefault("mcp_servers", {})
    skipped = []
    found, imported, needed = discover(skipped), [], set()
    if not found:
        print("No MCP servers found in: " + ", ".join(str(p) for _, p in claude_sources()))
        return 0
    for name, where, why in skipped:
        print("skip %-20s in %s: %s" % (name, where, why))
    for name, (label, server) in sorted(found.items()):
        if name in servers and not replace:
            print("skip %-20s already in your config (use --replace)" % name)
            continue
        if server.get("type") == "ws":
            print("skip %-20s from %s: a WebSocket server, which cd_AI does not connect to" % (name, label))
            continue
        clean, variables = sanitize(name, server)
        servers[name] = clean
        needed.update(variables)
        imported.append(name)
        print("%s %-20s from %s" % ("would import" if dry_run else "import", name, label))
        if clean.get("url") and not clean.get("headers"):  # a remote that signs you in (OAuth) in Claude
            print("    %s: no token header: cd_AI's own calls get one from \"headers\" (Claude Code, as an "
                  "agent, signs in itself)" % name)
    if not dry_run and imported:
        config.save(data, path)
        print("Wrote %s." % path)
    if needed:
        print("Set these in the environment Claudish runs in: %s" % ", ".join(sorted(needed)))
    if imported:
        print(as_typed('Next: `claudish mcp list` shows their tools; use one in a profile\'s "context" or a binding, e.g.\n'
                       '  {"type": "mcp", "server": "%s", "tool": "TOOL", "arguments": {}}' % imported[0]))
    return 0


def list_servers():
    from .doctor import marks
    shown = marks()
    from .context import list_server
    from .service import as_typed
    data = read_config(Path(config.default_path()))
    servers = data.get("mcp_servers") or {}
    if not servers:
        print(as_typed("No MCP servers configured; `claudish mcp import` copies the ones you use with Claude."))
        return 0
    status = 0
    for name, server in servers.items():
        try:
            listing = list_server(server, name=name)
        except Exception as exc:
            print("%s %s: %s" % (shown["fail"], name, exc))
            status = 1
            continue
        print("%s %s: %d tools, %d resources" % (shown["ok"], name, len(listing["tools"]), len(listing["resources"])))
        for tool, summary in listing["tools"]:
            print("    tool %-28s %s" % (tool, summary[:70]))
        for uri in listing["resources"]:
            print("    resource %s" % uri)
    return status


def autocompletes(settings):
    """Whether continue asks this profile's model at every pause (model.Rewriter.autocompletes)."""
    return settings["backend"] == "rules" or (settings["backend"] in ("llama", "openai")
                                              and config.loopback(settings.get("model_url") or ""))


def context_test(app, profile=None, show=False):
    from .doctor import marks
    shown = marks()
    name, settings, _, context = config.resolve(profile=profile)
    # Which AI answers there: the app's binding, then that profile's choice per mode; the context is
    # what that profile consults (its own, and the service profile's bindings for the app), as the service does.
    answering = next((b.profile for b in settings.get("bindings") or [] if b.matches(app) and b.profile), None) or name
    _, routed, _, _ = config.resolve(profile=answering) if answering != name else (None, settings, None, None)
    bindings = [b for b in settings.get("bindings") or [] if b.matches(app)]  # the service's: a routed profile gets them
    print("App %r, profile %r: %d binding(s) match" % (app, answering, len(bindings)))
    # Each mode as the service answers it (Rewriter.route, continues); the context is the service's
    # own and the app's bindings', whichever profile answers.
    for mode in ("continue", "rewrite", "instruct"):
        chosen = (routed["modes"].get(mode) or {}).get("profile") or answering
        _, chosen_settings, _, _ = config.resolve(profile=chosen) if chosen != name else (None, settings, None, None)
        if mode == "continue" and chosen == answering and not autocompletes(chosen_settings):
            print("  %-9s not asked: %r is a hosted model and no profile routes continue (it types as is)"
                  % (mode, chosen))
            continue
        print("  %-9s answered by profile %r (%s)" % (mode, chosen, chosen_settings["backend"]))
    providers = [("context", p) for p in (context.providers if context else [])] + \
                [("binding %s" % b.pattern, p) for b in bindings for p in b.providers]
    print("%d provider(s) would be consulted" % len(providers))
    status = 0
    for origin, provider in providers:
        text = provider.get()
        if text is None:
            print("%s %-28s (%s) %s" % (shown["fail"], provider.name, origin, getattr(provider, "error", "failed")))
            status = 1
        else:
            print("%s %-28s (%s) %d characters" % (shown["ok"], provider.name, origin, len(text)))
            if show:
                print("    " + text[:300].replace("\n", "\n    "))
    return status
