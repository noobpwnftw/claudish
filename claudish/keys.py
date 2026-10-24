"""API keys where the service can read them and config.json never holds them (G61, G62).

The environment comes first (ANTHROPIC_API_KEY, or a profile's api_key_env); then the key cd_AI's
settings saved for the service: the macOS Keychain. A service started at login sees no shell
variables, so on macOS the Keychain is how a key reaches it. Windows and Linux stores: G62.
"""
import subprocess
import sys

SERVICE = "cd_AI"  # the Keychain item's service; its account names the provider ("anthropic")
SECURITY = "/usr/bin/security"


def stored(name="anthropic"):
    """The key saved for this provider, or None."""
    if sys.platform != "darwin":
        return None
    try:
        found = subprocess.run([SECURITY, "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
                               capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return found.stdout.strip() or None if found.returncode == 0 else None


def store(key, name="anthropic"):
    """Save (or replace) the key for this provider. ValueError where there is no store yet."""
    if sys.platform != "darwin":
        raise ValueError("no key store on this system yet: set ANTHROPIC_API_KEY in your user environment "
                         "(docs/install.md)")
    # `security` takes the key as an argument (with -w last and no value it would prompt on the
    # terminal instead); it is briefly in the process list, to this user's processes, and never in a
    # file or a log.
    subprocess.run([SECURITY, "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w", key],
                   check=True, capture_output=True, timeout=10)
