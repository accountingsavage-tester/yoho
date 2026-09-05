from __future__ import annotations

import enum
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

ADB_TIMEOUT = 10


class ActionType(enum.Enum):
    TAP = "TAP"
    TYPE = "TYPE"
    SWIPE = "SWIPE"
    KEYEVENT = "KEYEVENT"
    HOME = "HOME"
    BACK = "BACK"
    SAY = "SAY"


@dataclass(frozen=True)
class AndroidAction:
    type: ActionType
    value: Any = None


class ActionParseError(ValueError):
    pass


class ADBError(RuntimeError):
    pass


def adb(serial: str | None, *args: str, timeout: int = ADB_TIMEOUT) -> str:
    executable = shutil.which("adb")
    if executable is None:
        raise ADBError("ADB executable was not found.")
    command = [executable]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ADBError("ADB command timed out.") from exc
    except OSError as exc:
        raise ADBError(f"ADB could not start: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        if "no devices" in detail.lower() or "device not found" in detail.lower() or "offline" in detail.lower():
            raise ADBError("No Android device is connected or the device is offline.")
        raise ADBError(f"ADB command failed: {detail or 'unknown error'}")
    return result.stdout.strip()


def check_adb(serial: str | None) -> tuple[bool, str]:
    executable = shutil.which("adb")
    if executable is None:
        return False, "ADB executable was not found."
    try:
        output = adb(serial, "get-state", timeout=5)
    except ADBError as exc:
        return False, str(exc)
    if output.strip() != "device":
        return False, f"ADB device is unavailable (state: {output or 'unknown'})."
    return True, serial or "default device"


def dump_ui(serial: str | None) -> ET.Element:
    adb(serial, "shell", "uiautomator", "dump", "/sdcard/jarvis-ui.xml")
    xml = adb(serial, "exec-out", "cat", "/sdcard/jarvis-ui.xml")
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ADBError("Android returned malformed UI XML.") from exc


def parse_elements(root: ET.Element) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for node in root.iter("node"):
        attrs = node.attrib
        label = (attrs.get("text") or attrs.get("content-desc") or "").strip()
        bounds = attrs.get("bounds", "")
        if not label or not bounds:
            continue
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not match:
            continue
        x1, y1, x2, y2 = map(int, match.groups())
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
            continue
        elements.append({
            "label": label[:200],
            "text": attrs.get("text", ""),
            "content_desc": attrs.get("content-desc", ""),
            "clickable": attrs.get("clickable") == "true",
            "enabled": attrs.get("enabled", "true") == "true",
            "focusable": attrs.get("focusable") == "true",
            "editable": attrs.get("class", "") in {
                "android.widget.EditText", "android.widget.AutoCompleteTextView"
            } or attrs.get("inputType", "") not in {"", "none"},
            "class_name": attrs.get("class", ""),
            "x": (x1 + x2) // 2,
            "y": (y1 + y2) // 2,
        })
    return elements


def format_elements(elements: list[dict[str, Any]]) -> str:
    lines = []
    for i, el in enumerate(elements, 1):
        flags = []
        if el["clickable"]: flags.append("clickable")
        if el["focusable"]: flags.append("focusable")
        if el["editable"]: flags.append("editable")
        lines.append(f"{i}. [{' '.join(flags) or 'text'}] {el['label']}")
    return "\n".join(lines) or "No usable visible elements."


def _element(elements: list[dict[str, Any]], index: int) -> dict[str, Any]:
    if index < 1 or index > len(elements):
        raise ActionParseError("Invalid UI element index.")
    element = elements[index - 1]
    if not element["enabled"]:
        raise ActionParseError("The selected UI element is disabled.")
    return element


def parse_action(response: str, elements: list[dict[str, Any]] | None = None) -> AndroidAction:
    lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
    if len(lines) != 1:
        raise ActionParseError("LLM must return exactly one action line.")
    line = lines[0]
    match = re.fullmatch(r"ACTION:\s*([A-Z]+)(?:\s+(.*))?", line, re.IGNORECASE)
    if not match:
        raise ActionParseError("Invalid Android action format.")
    name = match.group(1).upper()
    rest = match.group(2) or ""
    try:
        action_type = ActionType(name)
    except ValueError as exc:
        raise ActionParseError(f"Unknown Android action: {name}") from exc

    if action_type in {ActionType.HOME, ActionType.BACK}:
        if rest:
            raise ActionParseError(f"{name} does not accept arguments.")
        return AndroidAction(action_type)
    if action_type is ActionType.SAY:
        if not rest.strip():
            raise ActionParseError("SAY requires non-empty text.")
        return AndroidAction(action_type, rest)
    if action_type is ActionType.SWIPE:
        direction = rest.strip().lower()
        if direction not in {"up", "down", "left", "right"}:
            raise ActionParseError("Invalid swipe direction.")
        return AndroidAction(action_type, direction)
    if action_type is ActionType.KEYEVENT:
        if not re.fullmatch(r"\d+", rest.strip()):
            raise ActionParseError("KEYEVENT requires a numeric Android keyevent code.")
        return AndroidAction(action_type, int(rest))
    if action_type is ActionType.TAP:
        if not re.fullmatch(r"\d+", rest.strip()):
            raise ActionParseError("TAP requires exactly one UI element index.")
        index = int(rest)
        if elements is not None:
            element = _element(elements, index)
            if not element["clickable"]:
                raise ActionParseError("TAP requires a clickable UI element.")
        return AndroidAction(action_type, index)
    if action_type is ActionType.TYPE:
        match = re.fullmatch(r"(\d+)\s+(.+)", rest, re.DOTALL)
        if not match:
            raise ActionParseError("TYPE requires an element index and non-empty text.")
        index, text = int(match.group(1)), match.group(2)
        if elements is not None:
            element = _element(elements, index)
            if not (element["editable"] or element["focusable"]):
                raise ActionParseError("TYPE requires an editable or focusable input element.")
        return AndroidAction(action_type, (index, text))
    raise ActionParseError("Unsupported Android action.")


def tap(serial: str | None, element: dict[str, Any]) -> None:
    if not element.get("enabled") or not element.get("clickable"):
        raise ADBError("Selected element cannot be tapped.")
    adb(serial, "shell", "input", "tap", str(element["x"]), str(element["y"]))


def type_text(serial: str | None, element: dict[str, Any], text: str) -> None:
    if not element.get("enabled") or not (element.get("editable") or element.get("focusable")):
        raise ADBError("Selected element cannot receive text.")
    tap_target = element
    if element.get("clickable"):
        tap(serial, tap_target)
    adb(serial, "shell", "input", "text", text.replace(" ", "%s"))


def swipe(serial: str | None, direction: str) -> None:
    moves = {"up": (540, 1600, 540, 400), "down": (540, 400, 540, 1600), "left": (900, 800, 100, 800), "right": (100, 800, 900, 800)}
    if direction not in moves:
        raise ADBError("Invalid swipe direction.")
    x1, y1, x2, y2 = moves[direction]
    adb(serial, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "200")


def keyevent(serial: str | None, code: int) -> None:
    if code < 0:
        raise ADBError("Invalid keyevent code.")
    adb(serial, "shell", "input", "keyevent", str(code))
