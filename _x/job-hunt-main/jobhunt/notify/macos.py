"""Native macOS banners, for when he's actually at the machine.

Prefers terminal-notifier when installed. The osascript fallback works, but
its notifications are attributed to Script Editor, whose alert style
defaults to None on Sequoia — so they land silently in Notification Center
and never appear as a banner. Script Editor also doesn't show up in System
Settings until it has been launched once, which makes that state hard to
fix and easy to mistake for "notifications are broken".

    brew install terminal-notifier
"""

from __future__ import annotations

import platform
import shutil
import subprocess

APP_ICON = "com.apple.Safari"  # any bundle id; gives the banner a sane icon


def _notifier() -> str | None:
    return shutil.which("terminal-notifier")


def available() -> bool:
    if platform.system() != "Darwin":
        return False
    return bool(_notifier() or shutil.which("osascript"))


def backend() -> str:
    if platform.system() != "Darwin":
        return "unavailable"
    if _notifier():
        return "terminal-notifier"
    if shutil.which("osascript"):
        return "osascript (via Script Editor — check its alert style)"
    return "unavailable"


def send(title: str, subtitle: str = "", body: str = "",
         url: str | None = None) -> bool:
    if platform.system() != "Darwin":
        return False

    notifier = _notifier()
    if notifier:
        cmd = [notifier, "-title", title, "-message", body or subtitle,
               "-sound", "Glass", "-sender", APP_ICON]
        if subtitle and body:
            cmd += ["-subtitle", subtitle]
        if url:
            cmd += ["-open", url]
        return _run(cmd)

    if not shutil.which("osascript"):
        return False
    script = (
        f"display notification {_q(body)} with title {_q(title)} "
        f"subtitle {_q(subtitle)} sound name \"Glass\""
    )
    return _run(["osascript", "-e", script])


def _run(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def _q(text: str) -> str:
    """AppleScript string literal — only backslash and quote need escaping."""
    escaped = (text or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
