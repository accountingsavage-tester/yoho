import re
from core.llm import run_llama
from tools import system as sys_tools
from tools import files as file_tools
from tools import utility
from tools import phone


def handle_control(config, goal, max_steps=8):
    serial = config.get("adb_serial")
    if not serial:
        return "ADB control is not configured. Use direct Android commands for this phone."
    for _ in range(max_steps):
        try:
            root = sys_tools.dump_ui(serial)
            elements = sys_tools.parse_elements(root)
            prompt = (
                "<|system|>\n" + config["prompts"]["control"] +
                "\nAllowed actions: TAP <id>, TYPE <id> <text>, SWIPE up|down|left|right, "
                "HOME, BACK, SAY <text>. Return exactly one ACTION line.\n<|user|>\n" +
                "GOAL: " + goal + "\nSCREEN:\n" + sys_tools.format_elements(elements) +
                "\n<|assistant|>"
            )
            response, code, err = run_llama(config["model"], prompt, n=40, context_size=config["context_size"], timeout=config.get("llm_timeout", 60))
            action, rest = sys_tools.parse_action(response)
            print("JARVIS action: " + response)
            if action == "DONE": return "Done."
            if action == "SAY": return rest
            if action == "HOME": sys_tools.keyevent(serial, 3)
            elif action == "BACK": sys_tools.keyevent(serial, 4)
            elif action == "TAP":
                idx = int(rest) - 1
                if not 0 <= idx < len(elements): return "Invalid UI element."
                sys_tools.tap(serial, elements[idx])
            elif action == "TYPE":
                m = re.fullmatch(r"(\d+)\s+(.+)", rest, re.S)
                if not m: return "Invalid TYPE action."
                idx = int(m.group(1)) - 1
                if not 0 <= idx < len(elements): return "Invalid UI element."
                sys_tools.type_text(serial, elements[idx], m.group(2))
            elif action == "SWIPE": sys_tools.swipe(serial, rest.lower())
        except (RuntimeError, ValueError, sys_tools.ActionParseError) as exc:
            return "Android control error: " + str(exc)
    return "Reached step limit."


def _phone_route(text):
    s = text.strip(); low = s.lower()
    if re.search(r"\b(battery|battery status|battery level|how much battery)\b", low): return phone.battery()
    if low in {"wifi", "wi-fi", "wifi status", "wi-fi status", "what's my wifi", "whats my wifi"}: return phone.wifi_info()
    if re.search(r"\b(turn|switch|enable|activate)\b.*\b(flashlight|torch)\b.*\b(on|enable)\b", low) or low in {"flashlight on", "torch on", "turn on flashlight", "turn on torch"}: return phone.flashlight(True)
    if re.search(r"\b(turn|switch|disable|deactivate)\b.*\b(flashlight|torch)\b.*\b(off|disable)\b", low) or low in {"flashlight off", "torch off", "turn off flashlight", "turn off torch"}: return phone.flashlight(False)
    m = re.search(r"(?:vibrate|vibration).*?(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)", low)
    if m: return phone.vibrate(int(float(m.group(1)) * 1000))
    if low in {"vibrate", "make the phone vibrate"}: return phone.vibrate(1000)
    if low in {"read my clipboard", "what's on my clipboard", "whats on my clipboard", "get clipboard", "clipboard"}: return phone.clipboard_get()
    m = re.match(r"(?:copy|put)\s+(.+?)\s+(?:to|on|into)\s+(?:my\s+)?clipboard$", s, re.I)
    if m: return phone.clipboard_set(m.group(1))
    m = re.match(r"set (?:my )?clipboard (?:to|as)\s+(.+)$", s, re.I)
    if m: return phone.clipboard_set(m.group(1))
    m = re.match(r"(?:send|show|create) (?:me )?(?:a )?(?:notification|alert)(?: saying| that says|:)\s*(.+)$", s, re.I)
    if m: return phone.notify("JARVIS", m.group(1))
    m = re.match(r"(?:show|display) (?:an )?android (?:popup|toast)[: ]+(.+)$", s, re.I)
    if m: return phone.toast(m.group(1))
    if re.search(r"\b(turn|switch|enable)\s+(?:the\s+)?(?:wi[- ]?fi)\s+(on|enable)\b", low): return phone.wifi(True)
    if re.search(r"\b(turn|switch|disable)\s+(?:the\s+)?(?:wi[- ]?fi)\s+(off|disable)\b", low): return phone.wifi(False)
    if low in {"where am i", "my location", "get my location", "find my location"}: return phone.location()
    if low in {"camera info", "show camera info", "what cameras do i have"}: return phone.camera_info()
    if low in {"take a photo", "take a picture", "take a photo for me", "take a picture for me"}: return phone.take_photo()
    m = re.match(r"(?:open|launch|start) (?:app )?([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)$", s, re.I)
    if m: return phone.open_app(m.group(1))
    m = re.match(r"(?:open|go to|browse)\s+(https?://\S+|[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/\S*)?)$", s, re.I)
    if m: return phone.open_url(m.group(1))
    if low in {"go home", "home screen", "open home screen"}: return phone.screen_home()
    if low in {"go back", "press back", "back"}: return phone.back()
    m = re.match(r"(?:set|change)\s+(music|ring|alarm|notification|system|call|voice_call)\s+volume\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?$", low)
    if m: return phone.volume(m.group(1), int(m.group(2)))
    return None


def route(config, context, memory, user_input):
    phone_response = _phone_route(user_input)
    if phone_response is not None: return phone_response
    if user_input.startswith("/control "): return handle_control(config, user_input[len("/control "):])
    if user_input.startswith("/read "): return file_tools.read_file(user_input[len("/read "):].strip())
    if user_input.startswith("/write "):
        rest = user_input[len("/write "):]
        if " " not in rest: return "Usage: /write <path> <content>"
        path, content = rest.split(" ", 1); return file_tools.write_file(path, content)
    if user_input.startswith("/ls"):
        parts = user_input.split(" ", 1); return file_tools.list_dir(parts[1].strip() if len(parts) > 1 else ".")
    if user_input.startswith("/time"): return utility.get_datetime()
    if user_input.startswith("/battery"): return phone.battery()
    if user_input.startswith("/calc "): return utility.calculate(user_input[len("/calc "):])
    context.add("user", user_input); memory.save_message("user", user_input)
    prompt = context.build_prompt(config["prompts"]["chat"])
    response, code, err = run_llama(config["model"], prompt, n=config["max_tokens"], context_size=config["context_size"], timeout=config.get("llm_timeout", 60))
    if not response:
        print("DEBUG returncode: " + str(code)); print("DEBUG stderr:\n" + err[-1000:]); response = "I had trouble generating a response."
    context.add("assistant", response); memory.save_message("assistant", response)
    return response
