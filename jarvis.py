from __future__ import annotations

import json
from pathlib import Path

from core.context import ConversationContext
from core.llm import check_llm
from core.router import route
from memory.memory import Memory
from tools.files import configure_sandbox
from tools.system import check_adb
from voice.tts import speak

BASE = Path(__file__).resolve().parent


def load_config() -> dict:
    try:
        config = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid config.json: {exc}") from exc
    required = {"model", "adb_serial", "context_size", "max_tokens", "llm_timeout", "workspace_path", "max_file_read_bytes", "max_context_messages", "prompts", "memory"}
    missing = sorted(required - config.keys())
    if missing: raise RuntimeError("missing configuration keys: " + ", ".join(missing))
    positive = ("context_size", "max_tokens", "llm_timeout", "max_file_read_bytes", "max_context_messages")
    for key in positive:
        if not isinstance(config[key], int) or config[key] <= 0: raise RuntimeError(f"config value {key} must be a positive integer")
    if not isinstance(config["model"], str) or not config["model"].strip(): raise RuntimeError("config value model must be a non-empty string")
    if not isinstance(config["adb_serial"], (str, type(None))): raise RuntimeError("config value adb_serial must be a string or null")
    if not isinstance(config["workspace_path"], str) or not config["workspace_path"].strip(): raise RuntimeError("workspace_path must be non-empty")
    if not isinstance(config["prompts"], dict) or not config["prompts"].get("chat") or not config["prompts"].get("control"): raise RuntimeError("prompts.chat and prompts.control are required")
    if not isinstance(config["memory"], dict) or not config["memory"].get("db_path"): raise RuntimeError("memory.db_path is required")
    workspace = (BASE / config["workspace_path"]).resolve()
    try: workspace.relative_to(BASE)
    except ValueError as exc: raise RuntimeError("workspace_path must be inside the repository") from exc
    config["workspace_path"] = workspace
    config["db_path"] = BASE / config["memory"]["db_path"]
    return config


def startup_report(config: dict, memory: Memory) -> str:
    configure_sandbox(config["workspace_path"], config["max_file_read_bytes"])
    adb_ok, adb_detail = check_adb(config["adb_serial"])
    llm_ok, llm_detail = check_llm(config["model"])
    return "\n".join([
        "Jarvis starting...",
        "Python: OK",
        "Workspace: OK",
        f"ADB: {'OK (' + adb_detail + ')' if adb_ok else 'unavailable (' + adb_detail + ')'}",
        f"LLM: {'OK' if llm_ok else 'unavailable (' + llm_detail + ')'}",
        "Memory: OK",
    ])


def main() -> None:
    try:
        config = load_config()
        memory = Memory(config["db_path"])
        configure_sandbox(config["workspace_path"], config["max_file_read_bytes"])
        context = ConversationContext(config["max_context_messages"])
        context.load(memory.recent_messages(min(config["memory"].get("recent_message_limit", config["max_context_messages"]), config["max_context_messages"])))
        print(startup_report(config, memory))
        print("Type /help for commands. Type exit to quit.")
        speak("JARVIS online.")
    except (RuntimeError, OSError) as exc:
        print("Error: " + str(exc)); return

    try:
        while True:
            try: user_input = input("\nYou: ").strip()
            except EOFError: break
            if not user_input: continue
            if user_input.lower() in {"exit", "quit", "/exit"}:
                print("JARVIS: Shutting down."); speak("Shutting down."); break
            try: response = route(config, context, memory, user_input)
            except Exception as exc: response = "Error: " + str(exc)
            print("JARVIS: " + response)
            speak(response)
    except KeyboardInterrupt:
        print("\nJARVIS: Shutting down.")
    finally:
        memory.close()


if __name__ == "__main__": main()
