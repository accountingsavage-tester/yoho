from core.llm import run_llama
from tools import system as sys_tools
from tools import files as file_tools
from tools import utility


def handle_control(config, goal, max_steps=8):
    serial = config["adb_serial"]
    for _ in range(max_steps):
        root = sys_tools.dump_ui(serial)
        elements = sys_tools.parse_elements(root)
        element_list = sys_tools.format_elements(elements)
        prompt = "<|system|>\n" + config["system_prompt_control"] + "\n<|user|>\nGOAL: " + goal + "\nSCREEN:\n" + element_list + "\n<|assistant|>\n"
        response, code, err = run_llama(config["model"], prompt, n=40, context_size=config["context_size"])
        action, rest = sys_tools.parse_action(response)
        print("JARVIS action: " + response)

        if action is None:
            return "I could not decide on an action."
        if action == "DONE":
            return "Done."
        if action == "SAY":
            return rest
        elif action == "TAP":
            import re
            m = re.search(r"\d+", rest)
            if m:
                idx = int(m.group()) - 1
                if 0 <= idx < len(elements):
                    sys_tools.tap(serial, elements[idx])
        elif action == "TYPE":
            import re
            m = re.match(r"(\d+)\s+(.*)", rest)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(elements):
                    sys_tools.type_text(serial, elements[idx], m.group(2))
        elif action == "SWIPE":
            sys_tools.swipe(serial, rest.lower())
        elif action == "BACK":
            sys_tools.keyevent(serial, 4)
        elif action == "HOME":
            sys_tools.keyevent(serial, 3)
        else:
            return "Unrecognized action: " + action
    return "Reached step limit."


def route(config, context, memory, user_input):
    if user_input.startswith("/control "):
        return handle_control(config, user_input[len("/control "):])

    if user_input.startswith("/read "):
        return file_tools.read_file(user_input[len("/read "):].strip())

    if user_input.startswith("/write "):
        rest = user_input[len("/write "):]
        if " " not in rest:
            return "Usage: /write <path> <content>"
        path, content = rest.split(" ", 1)
        return file_tools.write_file(path, content)

    if user_input.startswith("/ls"):
        parts = user_input.split(" ", 1)
        return file_tools.list_dir(parts[1].strip() if len(parts) > 1 else ".")

    if user_input.startswith("/time"):
        return utility.get_datetime()

    if user_input.startswith("/battery"):
        return utility.get_battery()

    if user_input.startswith("/calc "):
        return utility.calculate(user_input[len("/calc "):])

    context.add("user", user_input)
    memory.save_message("user", user_input)
    prompt = context.build_prompt(config["system_prompt_chat"])
    response, code, err = run_llama(config["model"], prompt, n=config["max_tokens"], context_size=config["context_size"])
    if not response:
        print("DEBUG returncode: " + str(code))
        print("DEBUG stderr:\n" + err[-1000:])
        response = "Sorry, I had trouble generating a response."
    context.add("assistant", response)
    memory.save_message("assistant", response)
    return response
