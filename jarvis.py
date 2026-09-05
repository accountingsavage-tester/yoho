import json
import os
from core.context import ConversationContext
from core.router import route
from memory.memory import Memory
from voice.tts import speak


def load_config():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "config.json")) as f:
        config = json.load(f)
    config["db_path"] = os.path.join(base, config["db_path"])
    return config


def main():
    config = load_config()
    memory = Memory(config["db_path"])
    context = ConversationContext()
    context.load(memory.recent_messages(20))

    print("JARVIS online.")
    speak("JARVIS online.")

    while True:
        try:
            user_input = input("\nYou: ").strip()
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
            break

    memory.close()


if __name__ == "__main__":
    main()
