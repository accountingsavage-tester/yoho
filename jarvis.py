import json
import os
from core.context import ConversationContext
from core.router import route
from memory.memory import Memory
from voice.tts import speak
from tools.files import configure_sandbox


def load_config():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "config.json"), encoding="utf-8") as f:
        config = json.load(f)
    config["db_path"] = os.path.join(base, config["memory"]["db_path"])
    config["workspace_path"] = os.path.join(base, config.get("workspace_path", "workspace"))
    return config


def main():
    config = load_config()
    configure_sandbox(config["workspace_path"], config.get("max_file_read_bytes", 1048576))
    memory = Memory(config["db_path"])
    context = ConversationContext()
    context.load(memory.recent_messages(20))

    print("JARVIS online.")
    speak("JARVIS online.")

    try:
        while True:
            try:
                user_input = input("\nYou: ").strip()
            except EOFError:
                break
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "/exit"):
                speak("Shutting down.")
                break
            response = route(config, context, memory, user_input)
            print("JARVIS: " + response)
            speak(response)
    except KeyboardInterrupt:
        speak("Shutting down.")
    finally:
        memory.close()


if __name__ == "__main__":
    main()
