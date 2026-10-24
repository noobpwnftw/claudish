"""MCP onboarding: import servers already set up for Claude, list their tools, and test context per app.

claudish mcp import [--dry-run] [--replace]   copy servers from Claude Desktop / Claude Code into the config
claudish mcp list                             connect to each configured server; show its tools and resources
claudish context test --app NAME              which bindings match NAME, and what each provider returns
Secrets are never copied: env and header values become "$NAME" references to your environment.
"""
import json
import os
import platform
import re
from pathlib import Path

from . import config


def claude_sources():
    """[(label, path)] of Claude configs that may define MCP servers."""
    home = Path.home()
    system = platform.system()
    desktop = (Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Claude" if system == "Windows"
               else home / "Library/Application Support/Claude" if system == "Darwin"
               else Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "Claude")
    return [("Claude Desktop", desktop / "claude_desktop_config.json"),
            ("Claude Code (user)", home / ".claude.json"),
            ("Claude Code (this project)", Path.cwd() / ".mcp.json")]


def discover():
    found = {}
    for label, path in claude_sources():
        try:
            servers = json.loads(path.read_text(encoding="utf-8")).get("mcpServers") or {}
        except (OSError, ValueError):
            continue
        for name, server in servers.items():
            if isinstance(server, dict) and name not in found:
                found[name] = (label, server)
    return found


def variable(*parts):
    return re.sub(r"[^A-Z0-9]+", "_", "_".join(parts).upper()).strip("_")


def sanitize(name, server):
    """(server for our config, [environment variables to set]). No secret value is copied."""
    needed, clean = [], {}
    if server.get("url"):
        clean["url"] = server["url"]
        if server.get("type") == "sse":
            clean["type"] = "sse"
        headers = {}
        for key, value in (server.get("headers") or {}).items():
            reference = re.fullmatch(r"(.*?)\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", str(value))
            if reference:  # "Bearer ${TOKEN}" -> "Bearer $TOKEN"
                headers[key] = "%s$%s" % (reference.group(1), reference.group(2))
                needed.append(reference.group(2))
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
            reference = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", str(value))
            env[key] = "$" + (reference.group(1) if reference else key)
            needed.append(reference.group(1) if reference else key)
        if env:
            clean["env"] = env
    return clean, needed


def import_servers(path=None, dry_run=False, replace=False):
    path = Path(path or config.default_path())
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(json.dumps(config.STARTER))
    servers = data.setdefault("mcp_servers", {})
    found, imported, needed = discover(), [], set()
    if not found:
        print("No MCP servers found in: " + ", ".join(str(p) for _, p in claude_sources()))
        return 0
    for name, (label, server) in sorted(found.items()):
        if name in servers and not replace:
            print("skip %-20s already in your config (use --replace)" % name)
            continue
        clean, variables = sanitize(name, server)
        servers[name] = clean
        needed.update(variables)
        imported.append(name)
        print("%s %-20s from %s" % ("would import" if dry_run else "import", name, label))
    if not dry_run and imported:
        if not path.exists():
            config.write_starter_templates(path)  # the starter's profiles read it
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("Wrote %s." % path)
    if needed:
        print("Secrets were not copied. Set these in the environment Claudish runs in: %s" % ", ".join(sorted(needed)))
    if imported:
        print('Next: `claudish mcp list` shows their tools; use one in a profile\'s "context" or a binding, e.g.\n'
              '  {"type": "mcp", "server": "%s", "tool": "TOOL", "arguments": {}}' % imported[0])
    return 0


def list_servers():
    from .context import list_server
    try:
        data = json.loads(Path(config.default_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    servers = data.get("mcp_servers") or {}
    if not servers:
        print("No MCP servers configured; `claudish mcp import` copies the ones you use with Claude.")
        return 0
    status = 0
    for name, server in servers.items():
        try:
            listing = list_server(server)
        except Exception as exc:
            print("✗ %s: %s" % (name, exc))
            status = 1
            continue
        print("✓ %s: %d tools, %d resources" % (name, len(listing["tools"]), len(listing["resources"])))
        for tool, summary in listing["tools"]:
            print("    tool %-28s %s" % (tool, summary[:70]))
        for uri in listing["resources"]:
            print("    resource %s" % uri)
    return status


def context_test(app, profile=None, show=False):
    name, settings, _, context = config.resolve(profile=profile)
    bindings = [b for b in settings.get("bindings") or [] if b.matches(app)]
    providers = [("profile", p) for p in (context.providers if context else [])] + \
                [("binding %s" % b.pattern, p) for b in bindings for p in b.providers]
    print("App %r, profile %r: %d binding(s) match, %d provider(s) would be consulted"
          % (app, name, len(bindings), len(providers)))
    # Which AI answers there: the app's binding, then that profile's choice per mode.
    answering = next((b.profile for b in bindings if b.profile), None) or name
    _, routed, _, _ = config.resolve(profile=answering) if answering != name else (None, settings, None, None)
    for mode in ("continue", "rewrite", "instruct"):
        chosen = (routed["modes"].get(mode) or {}).get("profile") or answering
        _, chosen_settings, _, _ = config.resolve(profile=chosen) if chosen != name else (None, settings, None, None)
        print("  %-9s answered by profile %r (%s%s)" % (mode, chosen, chosen_settings["backend"],
                                                       ", hosted" if chosen_settings.get("hosted") or
                                                       chosen_settings["backend"] == "claude" else ""))
    status = 0
    for origin, provider in providers:
        text = provider.get()
        if text is None:
            print("✗ %-28s (%s) %s" % (provider.name, origin, getattr(provider, "error", "failed")))
            status = 1
        else:
            print("✓ %-28s (%s) %d characters" % (provider.name, origin, len(text)))
            if show:
                print("    " + text[:300].replace("\n", "\n    "))
    return status
