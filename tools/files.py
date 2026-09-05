import os
from pathlib import Path


class SandboxError(Exception):
    pass


class FileSandbox:
    def __init__(self, root, max_read_bytes=1048576):
        self.root = Path(root).expanduser().resolve()
        self.max_read_bytes = int(max_read_bytes)
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, path):
        raw = Path(path)
        candidate = (self.root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise SandboxError("Path is outside the JARVIS workspace")
        return candidate

    def reject_symlink(self, path):
        current = path
        while current != self.root:
            if current.is_symlink():
                raise SandboxError("Symlinks are not allowed")
            current = current.parent

    def read(self, path):
        target = self.resolve(path)
        self.reject_symlink(target)
        if not target.is_file():
            raise SandboxError("File not found: " + str(path))
        if target.stat().st_size > self.max_read_bytes:
            raise SandboxError("File exceeds the read-size limit")
        return target.read_text(encoding="utf-8", errors="replace")

    def write(self, path, content):
        target = self.resolve(path)
        self.reject_symlink(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return "Saved to " + str(target.relative_to(self.root))

    def list_dir(self, path="."):
        target = self.resolve(path)
        self.reject_symlink(target)
        if not target.is_dir():
            raise SandboxError("Not a directory: " + str(path))
        return "\n".join(sorted(p.name for p in target.iterdir()))


_sandbox = None


def configure_sandbox(root, max_read_bytes=1048576):
    global _sandbox
    _sandbox = FileSandbox(root, max_read_bytes)


def _get():
    if _sandbox is None:
        configure_sandbox("workspace")
    return _sandbox


def read_file(path):
    try:
        return _get().read(path)
    except SandboxError as exc:
        return "Error: " + str(exc)


def write_file(path, content):
    try:
        return _get().write(path, content)
    except SandboxError as exc:
        return "Error: " + str(exc)


def list_dir(path="."):
    try:
        return _get().list_dir(path)
    except SandboxError as exc:
        return "Error: " + str(exc)
