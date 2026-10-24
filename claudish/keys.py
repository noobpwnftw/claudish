"""API keys where the service can read them and config.json never holds them (G61, G62).

The environment comes first (ANTHROPIC_API_KEY, or a profile's api_key_env); then the key saved in
cd_AI's settings: the Keychain on macOS, elsewhere a file beside the config that only this user can
read. A service started at login sees no shell variables, so a saved key is how one reaches it.
"""
import subprocess
import sys

SERVICE = "cd_AI"  # the Keychain item's service; its account names the provider ("anthropic")
SECURITY = "/usr/bin/security"


def key_file(name):
    from .config import default_path
    return default_path().with_name("%s.key" % name)


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


def where(name="anthropic"):
    """Where a saved key lives, in words for the settings window."""
    return "the Keychain" if sys.platform == "darwin" else str(key_file(name))
