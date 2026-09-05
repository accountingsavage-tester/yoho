from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path


def _run(command: list[str], timeout: int = 15, input_text: str | None = None) -> tuple[int, str, str]:
    executable = shutil.which(command[0])
    if executable is None:
        return 127, "", f"Command not found: {command[0]}"
    command[0] = executable
    try:
        result = subprocess.run(command, input=input_text, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out: {command[0]}"
    except OSError as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _result(code: int, out: str, err: str, success: str, failure: str) -> str:
    if code == 0: return success if not out else out
    return f"{failure} {err or out}".strip()


def battery() -> str:
    code, out, err = _run(["termux-battery-status"])
    if code: return _result(code, out, err, "", "Error: battery status unavailable.")
    try:
        d = json.loads(out); return f"Battery is {d.get('percentage', '?')}%. Status: {d.get('status', 'unknown')}. Temperature: {d.get('temperature', '?')} C."
    except json.JSONDecodeError: return out or "Error: invalid battery response."


def flashlight(on: bool) -> str:
    code, out, err = _run(["termux-torch", "on" if on else "off"])
    return _result(code, out, err, f"Flashlight {'on' if on else 'off'}.", "Error: could not control the flashlight.")


def vibrate(duration_ms: int = 1000, force: bool = False) -> str:
    duration_ms = max(1, min(int(duration_ms), 10000)); args = ["termux-vibrate", "-d", str(duration_ms)]
    if force: args.append("-f")
    code, out, err = _run(args)
    return _result(code, out, err, "Vibration complete.", "Error: could not vibrate the phone.")


def clipboard_get() -> str:
    code, out, err = _run(["termux-clipboard-get"])
    return out if code == 0 and out else (_result(code, out, err, "The clipboard is empty.", "Error: could not read the clipboard."))


def clipboard_set(text: str) -> str:
    if not text: return "Error: clipboard text is empty."
    code, out, err = _run(["termux-clipboard-set"], input_text=text)
    return _result(code, out, err, "Clipboard updated.", "Error: could not update the clipboard.")


def notify(title: str, content: str) -> str:
    code, out, err = _run(["termux-notification", "--title", title, "--content", content])
    return _result(code, out, err, "Notification sent.", "Error: could not send notification.")


def toast(message: str) -> str:
    code, out, err = _run(["termux-toast", message])
    return _result(code, out, err, "Toast shown.", "Error: could not show toast.")


def wifi_info() -> str:
    code, out, err = _run(["termux-wifi-connectioninfo"])
    if code: return _result(code, out, err, "", "Error: Wi-Fi information unavailable.")
    try:
        d = json.loads(out); return f"Wi-Fi network: {d.get('ssid') or 'unknown'}. IP: {d.get('ip') or d.get('ip_address') or 'unknown'}. State: {d.get('supplicant_state') or d.get('state') or 'unknown'}."
    except json.JSONDecodeError: return out or "Error: invalid Wi-Fi response."


def wifi(enable: bool) -> str:
    code, out, err = _run(["termux-wifi-enable", "true" if enable else "false"])
    return _result(code, out, err, f"Wi-Fi {'enabled' if enable else 'disabled'}.", "Error: could not change Wi-Fi state.")


def location() -> str:
    code, out, err = _run(["termux-location", "-p", "network", "-r", "once"], timeout=30)
    if code: return _result(code, out, err, "", "Error: location unavailable.")
    try:
        d = json.loads(out); return f"Location: latitude {d.get('latitude')}, longitude {d.get('longitude')}."
    except json.JSONDecodeError: return out or "Error: invalid location response."


def camera_info() -> str:
    code, out, err = _run(["termux-camera-info"])
    return _result(code, out, err, "Camera information unavailable.", "Error: camera information unavailable.")


def take_photo(path: str | None = None, camera: int = 0) -> str:
    target = Path(path).expanduser() if path else Path.home() / "storage" / "pictures" / f"jarvis_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    code, out, err = _run(["termux-camera-photo", "-c", str(1 if int(camera) == 1 else 0), str(target)], timeout=30)
    return _result(code, out, err, f"Photo saved to {target}.", "Error: could not take photo.")


def open_url(url: str) -> str:
    if not re.fullmatch(r"https?://[^\s]+", url, re.I): url = "https://" + url
    code, out, err = _run(["am", "start", "-a", "android.intent.action.VIEW", "-d", url])
    return _result(code, out, err, "Opened URL.", "Error: could not open URL.")


def open_app(package: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", package): return "Error: invalid Android package name."
    code, out, err = _run(["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
    return _result(code, out, err, f"Opened {package}.", "Error: could not open app.")


def screen_home() -> str:
    code, out, err = _run(["am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME"])
    return _result(code, out, err, "Home screen opened.", "Error: could not open home screen.")


def back() -> str:
    code, out, err = _run(["input", "keyevent", "4"])
    return _result(code, out, err, "Back pressed.", "Error: could not press Back.")


def volume(stream: str, level: int) -> str:
    if stream not in {"music", "ring", "alarm", "notification", "system", "call", "voice_call"}: return "Error: unsupported volume stream."
    level = max(0, min(int(level), 100))
    code, out, err = _run(["termux-volume", stream, str(level)])
    return _result(code, out, err, f"{stream} volume set to {level}.", "Error: could not change volume.")
