"""API keys where the service can read them (G61, G62).

The environment comes first (ANTHROPIC_API_KEY, or a profile's api_key_env); then the key saved in
cd_AI's settings: the Keychain on macOS, elsewhere a file beside the config. A service started at login sees no shell variables, so a saved key is how one reaches it.
"""
import subprocess
import sys

SERVICE = "cd_AI"  # the Keychain item's service; its account names the provider ("anthropic")
SECURITY = "/usr/bin/security"


def key_file(name):
    import hashlib
    from .config import default_path
    # A server's name is its address: a file name of its hash.
    plain = name if name.isidentifier() else "server-" + hashlib.sha256(name.encode()).hexdigest()[:16]
    return default_path().with_name("%s.key" % plain)


def stored(name="anthropic"):
    """The key saved for this provider, or None."""
    if sys.platform != "darwin":
        try:
            return key_file(name).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    try:
        found = subprocess.run([SECURITY, "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
                               capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return found.stdout.strip() or None if found.returncode == 0 else None


def claude_credential():
    """Where the claude backend's credential comes from, in the order it is used: ("environment",
    the variable), ("saved", None), ("profile", None) for an `ant auth login` profile, or (None, None)."""
    import os
    from pathlib import Path
    for variable in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        if os.environ.get(variable):
            return "environment", variable
    if stored():
        return "saved", None
    if anthropic_profile():
        return "profile", None
    return None, None


def anthropic_profile():
    """Whether the Anthropic SDK finds an `ant auth login` profile, where it looks: its config folder
    (ANTHROPIC_CONFIG_DIR, else %APPDATA%\\Anthropic on Windows, ~/.config/anthropic elsewhere), the
    active profile (ANTHROPIC_PROFILE, else the folder's active_config, else "default"), and that
    profile's configs/<profile>.json."""
    import os
    import sys
    from pathlib import Path
    if os.environ.get("ANTHROPIC_CONFIG_DIR"):
        folder = Path(os.environ["ANTHROPIC_CONFIG_DIR"])
    elif sys.platform == "win32":
        folder = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Anthropic"
    else:
        folder = Path.home() / ".config" / "anthropic"
    try:
        name = os.environ.get("ANTHROPIC_PROFILE") or (folder / "active_config").read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
    return (folder / "configs" / ("%s.json" % (name or "default"))).is_file()


def for_profile(settings):
    """The key a model server profile sends: its api_key_env's variable, else (an OpenAI-compatible
    server) the one saved in cd_AI's settings for its address, else None."""
    import os
    key = os.environ.get(settings["api_key_env"]) if settings.get("api_key_env") else None
    if not key and settings.get("backend") == "openai":
        key = server_key(settings["model_url"])
    return key


def store(key, name="anthropic"):
    """Save (or replace) the key for this provider."""
    if sys.platform != "darwin":
        from .client import write_private
        write_private(key_file(name), key)
        return
    # `security` takes the key as an argument (with -w last and no value it would prompt on the
    # terminal instead); it is briefly in the process list, to this user's processes, and never in a
    # file or a log.
    subprocess.run([SECURITY, "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w", key],
                   check=True, capture_output=True, timeout=10)


def forget(name="anthropic"):
    """Remove the key saved for this provider, if there is one."""
    if sys.platform != "darwin":
        key_file(name).unlink(missing_ok=True)
        return
    subprocess.run([SECURITY, "delete-generic-password", "-s", SERVICE, "-a", name], capture_output=True, timeout=10)


def server_name(url):
    """A model API's key is saved for its address: it goes to no other."""
    return "server " + url.strip().rstrip("/")


def server_key(url):
    return stored(server_name(url)) if url else None


def where(name="anthropic"):
    """Where a saved key lives, in words for the settings window."""
    return "the Keychain" if sys.platform == "darwin" else str(key_file(name))
