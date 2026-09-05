import enum
import re
import subprocess
import xml.etree.ElementTree as ET

ADB_TIMEOUT = 10


class ActionType(enum.Enum):
    TAP = "TAP"
    TYPE = "TYPE"
    SWIPE = "SWIPE"
    KEYEVENT = "KEYEVENT"
    HOME = "HOME"
    BACK = "BACK"
    SAY = "SAY"


class AndroidAction:
    def __init__(self, action_type, value=""):
        self.type = action_type
        self.value = value


class ActionParseError(ValueError):
    pass


def adb(serial, *args):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=ADB_TIMEOUT)
    except FileNotFoundError as exc:
        raise RuntimeError("adb was not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ADB command timed out") from exc
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ADB command failed")
    return result


def dump_ui(serial):
    adb(serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml")
    adb(serial, "pull", "/sdcard/ui.xml", "/tmp/jarvis-ui.xml")
    try:
        return ET.parse("/tmp/jarvis-ui.xml").getroot()
    except (OSError, ET.ParseError) as exc:
        raise RuntimeError("Could not parse Android UI XML") from exc


def parse_elements(root):
    elements = []
    for node in root.iter("node"):
        text = node.attrib.get("text", "").strip()
        desc = node.attrib.get("content-desc", "").strip()
        clickable = node.attrib.get("clickable") == "true"
        bounds = node.attrib.get("bounds", "")
        label = text or desc
        if not label or not bounds:
            continue
        m = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        if x2 <= x1 or y2 <= y1:
            continue
        elements.append({"label": label[:200], "clickable": clickable, "x": (x1+x2)//2, "y": (y1+y2)//2})
    return elements


def format_elements(elements):
    return "\n".join(
        f"{i}. [{'clickable' if el['clickable'] else 'text'}] {el['label']}"
        for i, el in enumerate(elements, 1)
    )


def tap(serial, el):
    adb(serial, "shell", "input", "tap", str(el["x"]), str(el["y"]))


def type_text(serial, el, text):
    tap(serial, el)
    escaped = text.replace(" ", "%s")
    adb(serial, "shell", "input", "text", escaped)


def swipe(serial, direction):
    moves = {
        "up": (540, 1600, 540, 400), "down": (540, 400, 540, 1600),
        "left": (900, 800, 100, 800), "right": (100, 800, 900, 800),
    }
    if direction not in moves:
        raise ValueError("Invalid swipe direction")
    x1, y1, x2, y2 = moves[direction]
    adb(serial, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "200")


def keyevent(serial, code):
    adb(serial, "shell", "input", "keyevent", str(code))


def parse_action(response):
    line = response.strip().splitlines()[0] if response.strip() else ""
    m = re.fullmatch(r"ACTION:\s*(TAP|TYPE|SWIPE|KEYEVENT|HOME|BACK|SAY|DONE)(?:\s+(.*))?", line, re.I)
    if not m:
        raise ActionParseError("Invalid action format")
    action = m.group(1).upper()
    rest = (m.group(2) or "").strip()
    return action, rest
