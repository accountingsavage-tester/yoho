class ConversationContext:
    def __init__(self):
        self.messages = []

    def load(self, messages):
        self.messages = list(messages)

    def add(self, role, content):
        self.messages.append({"role": role, "content": content})

    def build_prompt(self, system_prompt):
        lines = ["<|system|>", system_prompt]
        for message in self.messages:
            lines.append("<|" + message["role"] + "|>")
            lines.append(message["content"])
        lines.append("<|assistant|>")
        return "\n".join(lines)
