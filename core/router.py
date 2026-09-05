from __future__ import annotations

import re
import time
from typing import Any

from core.llm import run_llama
from tools import files as file_tools
from tools import phone
from tools import system as sys_tools
from tools import utility

HELP = "Commands: /help, /control <goal>, /read <path>, /write <path> <content>, /ls [path], /time, /battery, /calc <expression>. Natural language also supports phone controls."


def _phone_route(text: str) -> str | None:
    s, low = text.strip(), text.strip().lower()
    if low in {"battery", "battery status", "battery level", "what's my battery", "whats my battery"}: return phone.battery()
    if low in {"wifi", "wi-fi", "wifi status", "wi-fi status"}: return phone.wifi_info()
    if low in {"flashlight on", "torch on", "turn on flashlight", "turn on torch"}: return phone.flashlight(True)
    if low in {"flashlight off", "torch off", "turn off flashlight", "turn off torch"}: return phone.flashlight(False)
    if re.search(r"\b(turn|switch|enable)\b.*\b(flashlight|torch)\b.*\bon\b", low): return phone.flashlight(True)
    if re.search(r"\b(turn|switch|disable)\b.*\b(flashlight|torch)\b.*\boff\b", low): return phone.flashlight(False)
    match = re.search(r"(?:vibrate|vibration).*?(\d+(?:\.\d+)?)\s*(?:s|sec|second|seconds)\b", low)
    if match: return phone.vibrate(int(float(match.group(1)) * 1000))
    if low in {"vibrate", "make the phone vibrate"}: return phone.vibrate()
    if low in {"read my clipboard", "what's on my clipboard", "whats on my clipboard", "get clipboard", "clipboard"}: return phone.clipboard_get()
    match = re.match(r"(?:copy|put)\s+(.+?)\s+(?:to|on|into)\s+(?:my\s+)?clipboard$", s, re.I)
    if match: return phone.clipboard_set(match.group(1))
    match = re.match(r"set (?:my )?clipboard (?:to|as)\s+(.+)$", s, re.I)
    if match: return phone.clipboard_set(match.group(1))
    if re.search(r"\b(turn|switch|enable)\b.*\bwi[- ]?fi\b.*\bon\b", low): return phone.wifi(True)
    if re.search(r"\b(turn|switch|disable)\b.*\bwi[- ]?fi\b.*\boff\b", low): return phone.wifi(False)
    if low in {"where am i", "my location", "get my location"}: return phone.location()
    if low in {"camera info", "show camera info", "what cameras do i have"}: return phone.camera_info()
    if low in {"take a photo", "take a picture", "take a photo for me", "take a picture for me"}: return phone.take_photo()
    match = re.match(r"(?:open|launch|start)\s+(?:app\s+)?([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)$", s, re.I)
    if match: return phone.open_app(match.group(1))
    match = re.match(r"(?:open|go to|browse)\s+(https?://\S+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/\S*)?)$", s, re.I)
    if match: return phone.open_url(match.group(1))
    if low in {"go home", "home screen", "open home screen"}: return phone.screen_home()
    if low in {"go back", "press back", "back"}: return phone.back()
    match = re.match(r"(?:set|change)\s+(music|ring|alarm|notification|system|call|voice_call)\s+volume\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?$", low)
    if match: return phone.volume(match.group(1), int(match.group(2)))
    return None


def diagnostics(config: dict[str, Any], memory: Any) -> str:
    adb_ok, adb_detail = sys_tools.check_adb(config.get("adb_serial"))
    from core.llm import check_llm
    llm_ok, llm_detail = check_llm(config.get("model", ""))
    workspace_ok = True
    try: file_tools._get().list_dir(".")
    except Exception: workspace_ok = False
    memory_ok = memory is not None
    return "\n".join([
        "Jarvis starting...",
        "Python: OK",
        f"Workspace: {'OK' if workspace_ok else 'unavailable'}",
        f"ADB: {'OK (' + adb_detail + ')' if adb_ok else 'unavailable (' + adb_detail + ')'}",
        f"LLM: {'OK' if llm_ok else 'unavailable (' + llm_detail + ')'}",
        f"Memory: {'OK' if memory_ok else 'unavailable'}",
    ])


def handle_control(config: dict[str, Any], goal: str, max_steps: int = 8) -> str:
    serial = config.get("adb_serial")
    if not goal.strip(): return "Error: /control requires a goal."
    ok, detail = sys_tools.check_adb(serial)
    if not ok: return "Error: ADB device is unavailable. " + detail
    for _ in range(max_steps):
        try:
            elements = sys_tools.parse_elements(sys_tools.dump_ui(serial))
            prompt = ("<|system|>\n" + config["prompts"]["control"] + "\n<|user|>\nGOAL: " + goal +
                      "\nVISIBLE ELEMENTS:\n" + sys_tools.format_elements(elements) + "\n<|assistant|>")
            response, code, err = run_llama(config["model"], prompt, n=40, context_size=config["context_size"], timeout=config["llm_timeout"])
            if code != 0: return "Error: LLM control failed: " + err
            action = sys_tools.parse_action(response, elements)
            if action.type is sys_tools.ActionType.SAY: return action.value
            if action.type is sys_tools.ActionType.HOME: sys_tools.keyevent(serial, 3)
            elif action.type is sys_tools.ActionType.BACK: sys_tools.keyevent(serial, 4)
            elif action.type is sys_tools.ActionType.TAP: sys_tools.tap(serial, elements[action.value - 1])
            elif action.type is sys_tools.ActionType.TYPE:
                index, text = action.value; sys_tools.type_text(serial, elements[index - 1], text)
            elif action.type is sys_tools.ActionType.SWIPE: sys_tools.swipe(serial, action.value)
            elif action.type is sys_tools.ActionType.KEYEVENT: sys_tools.keyevent(serial, action.value)
            time.sleep(0.25)
        except (sys_tools.ADBError, sys_tools.ActionParseError, ValueError) as exc:
            return "Error: " + str(exc)
    return "Error: Android control reached the step limit."


def route(config: dict[str, Any], context: Any, memory: Any, user_input: str) -> str:
    phone_response = _phone_route(user_input)
    if phone_response is not None: return phone_response
    if user_input.strip() == "/help": return HELP
    if user_input.startswith("/control "): return handle_control(config, user_input[len("/control "):])
    if user_input.startswith("/read "): return file_tools.read_file(user_input[len("/read "):].strip())
    if user_input.startswith("/write "):
        rest = user_input[len("/write "):]
        if " " not in rest: return "Error: Usage /write <path> <content>"
        path, content = rest.split(" ", 1); return file_tools.write_file(path, content)
    if user_input == "/ls" or user_input.startswith("/ls "):
        return file_tools.list_dir(user_input[3:].strip() or ".")
    if user_input == "/time": return utility.get_datetime()
    if user_input == "/battery": return phone.battery()
    if user_input.startswith("/calc "): return utility.calculate(user_input[len("/calc "):])
    if user_input == "/diagnostics": return diagnostics(config, memory)

    context.add("user", user_input); memory.save_message("user", user_input)
    response, code, err = run_llama(config["model"], context.build_prompt(config["prompts"]["chat"]), n=config["max_tokens"], context_size=config["context_size"], timeout=config["llm_timeout"])
    if code != 0 or not response:
        response = "Error: " + err if err else "Error: LLM returned no response."
    context.add("assistant", response); memory.save_message("assistant", response)
    return response
