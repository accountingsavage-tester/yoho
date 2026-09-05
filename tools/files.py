import os


def read_file(path):
    if not os.path.isfile(path):
        return "File not found: " + path
    with open(path, "r", errors="ignore") as f:
        return f.read()


def write_file(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return "Saved to " + path


def list_dir(path="."):
    if not os.path.isdir(path):
        return "Not a directory: " + path
    return "\n".join(sorted(os.listdir(path)))
