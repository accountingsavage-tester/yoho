"""Android/Termux control layer for JARVIS.

Uses Termux:API and Android's public `am` interface. No root is required.
The LLM never receives arbitrary shell access; router calls these fixed methods.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path


def _run(command, timeout=15, input_text=None):
    try:
        p = subprocess.run(command, input=input_text, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"Command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out: {command[0]}"


def _api(command, *args, timeout=15):
    return _run([command, *map(str, args)], timeout=timeout)


def _ok(code, stdout, stderr, fallback):
    if code == 0:
        return stdout
    detail = stderr or stdout
    if "not found" in detail.lower() or code == 127:
        return f"{fallback} The required Termux command is not installed."
    return f"{fallback} {detail}" if detail else fallback


def battery():
    code, out, err = _api("termux-battery-status")
    if code != 0:
        return _ok(code, out, err, "I couldn't read the battery status.")
    try:
        d = json.loads(out)
        return f"Battery {d.get('percentage', '?')} percent, {str(d.get('status', 'unknown')).lower()}, {d.get('temperature', '?')} degrees Celsius."
    except Exception:
        return out or "Battery status unavailable."


def flashlight(on=None):
    if on is None:
        return "Tell me whether to turn the flashlight on or off."
    value = "on" if on else "off"
    code, out, err = _api("termux-torch", value)
    return _ok(code, out, err, f"I couldn't turn the flashlight {value}.") or f"Flashlight {value}."


def vibrate(duration_ms=1000, force=False):
    duration_ms = max(1, min(int(duration_ms), 10000))
    args = ["-d", duration_ms]
    if force:
        args.append("-f")
    code, out, err = _api("termux-vibrate", *args)
    return _ok(code, out, err, "I couldn't vibrate the phone.") or "Done."


def clipboard_get():
    code, out, err = _api("termux-clipboard-get")
    if code != 0:
        return _ok(code, out, err, "I couldn't read the clipboard.")
    return out if out else "The clipboard is empty."


def clipboard_set(text):
    if not text:
        return "I need text to put on the clipboard."
    code, out, err = _api("termux-clipboard-set", text)
    return _ok(code, out, err, "I couldn't set the clipboard.") or "Copied to the clipboard."


def notify(title, content):
    code, out, err = _api("termux-notification", "-t", title, "-c", content)
    return _ok(code, out, err, "I couldn't create the notification.") or "Notification sent."


def toast(message):
    code, out, err = _api("termux-toast", message)
    return _ok(code, out, err, "I couldn't show the Android popup.") or "Done."


def wifi_info():
    code, out, err = _api("termux-wifi-connectioninfo")
    if code != 0:
        return _ok(code, out, err, "I couldn't read Wi-Fi information.")
    try:
        d = json.loads(out)
        ssid = d.get("ssid") or "unknown network"
        state = d.get("supplicant_state") or d.get("state") or "unknown"
        ip = d.get("ip") or d.get("ip_address") or "unknown IP"
        return f"Wi-Fi is {str(state).lower()}, network {ssid}, IP {ip}."
    except Exception:
        return out or "Wi-Fi information unavailable."


def wifi(enable):
    value = "true" if enable else "false"
    code, out, err = _api("termux-wifi-enable", value)
    return _ok(code, out, err, f"I couldn't turn Wi-Fi {'on' if enable else 'off'}.") or f"Wi-Fi {'on' if enable else 'off'}."


def location():
    code, out, err = _api("termux-location", "-p", "network", "-r", "once", timeout=30)
    if code != 0:
        return _ok(code, out, err, "I couldn't get your location.")
    try:
        d = json.loads(out)
        lat = d.get("latitude")
        lon = d.get("longitude")
        if lat is None or lon is None:
            return "Location data was unavailable."
        return f"Your approximate location is latitude {lat}, longitude {lon}."
    except Exception:
        return out or "Location unavailable."


def camera_info():
    code, out, err = _api("termux-camera-info")
    return _ok(code, out, err, "I couldn't access camera information.") or "Camera information unavailable."


def take_photo(path=None, camera=0):
    if path is None:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = str(Path.home() / "storage" / "pictures" / f"jarvis_{stamp}.jpg")
    path = os.path.expanduser(path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    camera = 1 if int(camera) == 1 else 0
    code, out, err = _api("termux-camera-photo", "-c", camera, path, timeout=30)
    if code != 0:
        return _ok(code, out, err, "I couldn't take the photo.")
    return f"Photo saved to {path}."


def open_url(url):
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    code, out, err = _run(["am", "start", "-a", "android.intent.action.VIEW", "-d", url])
    return _ok(code, out, err, "I couldn't open that URL.") or "Opened it."


def open_app(package):
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", package):
        return "That doesn't look like a valid Android package name."
    code, out, err = _run(["monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
    return _ok(code, out, err, f"I couldn't open {package}.") or f"Opened {package}."


def screen_home():
    code, out, err = _run(["am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME"])
    return _ok(code, out, err, "I couldn't return to the home screen.") or "Home screen opened."


def back():
    code, out, err = _run(["input", "keyevent", "4"])
    return _ok(code, out, err, "I couldn't go back.") or "Done."


def volume(stream, level):
    allowed = {"music", "ring", "alarm", "notification", "system", "call", "voice_call"}
    if stream not in allowed:
        return "Unsupported volume stream."
    level = max(0, min(int(level), 100))
    code, out, err = _api("termux-volume", stream, level)
    return _ok(code, out, err, "I couldn't change the volume.") or f"{stream} volume set to {level}."
