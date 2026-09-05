import subprocess
import re
import xml.etree.ElementTree as ET


def adb(serial, *args):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def dump_ui(serial):
    adb(serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml")
    adb(serial, "pull", "/sdcard/ui.xml", "/tmp/ui.xml")
    tree = ET.parse("/tmp/ui.xml")
    return tree.getroot()


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
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        elements.append({"label": label, "clickable": clickable, "x": cx, "y": cy})
    return elements


def format_elements(elements):
    lines = []
    for i, el in enumerate(elements, 1):
        tag = "clickable" if el["clickable"] else "text"
        lines.append(str(i) + ". [" + tag + "] " + el["label"])
    return "\n".join(lines)


def tap(serial, el):
    adb(serial, "shell", "input", "tap", str(el["x"]), str(el["y"]))


def type_text(serial, el, text):
    tap(serial, el)
    escaped = text.replace(" ", "%s")
    adb(serial, "shell", "input", "text", escaped)


def swipe(serial, direction):
    moves = {
        "up": (540, 1600, 540, 400),
        "down": (540, 400, 540, 1600),
        "left": (900, 800, 100, 800),
        "right": (100, 800, 900, 800),
    }
    x1, y1, x2, y2 = moves.get(direction, moves["up"])
    adb(serial, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "200")


def keyevent(serial, code):
    adb(serial, "shell", "input", "keyevent", str(code))


def parse_action(response):
    m = re.search(r"ACTION:\s*(\w+)(.*)", response)
    if not m:
        return None, None
    return m.group(1).upper(), m.group(2).strip()
