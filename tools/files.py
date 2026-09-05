from __future__ import annotations

import os
from pathlib import Path


class SandboxError(RuntimeError):
    pass


class FileSandbox:
    def __init__(self, root: str | Path, max_read_bytes: int = 1048576):
        self.root = Path(root).expanduser().resolve()
        if max_read_bytes < 1:
            raise SandboxError("max_file_read_bytes must be positive")
        self.max_read_bytes = int(max_read_bytes)
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise SandboxError("Workspace itself cannot be a symlink")

    def resolve(self, path: str | Path) -> Path:
        raw = Path(path)
        if raw.is_absolute():
            candidate = raw.expanduser().resolve(strict=False)
        else:
            candidate = (self.root / raw).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise SandboxError("workspace path is outside the allowed directory") from exc
        self._check_parents(candidate)
        return candidate

    def _check_parents(self, target: Path) -> None:
        current = target
        while current != self.root:
            if current.is_symlink():
                raise SandboxError("symlink escapes are not allowed")
            current = current.parent
        if self.root.is_symlink():
            raise SandboxError("workspace itself cannot be a symlink")

    def read(self, path: str | Path) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise SandboxError("file not found")
        size = target.stat().st_size
        if size > self.max_read_bytes:
            raise SandboxError(f"file exceeds the {self.max_read_bytes}-byte read limit")
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise SandboxError(f"could not read file: {exc}") from exc

    def write(self, path: str | Path, content: str) -> str:
        target = self.resolve(path)
        if target.exists() and not target.is_file():
            raise SandboxError("target is not a regular file")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._check_parents(target)
        try:
            target.write_text(str(content), encoding="utf-8")
        except OSError as exc:
            raise SandboxError(f"could not write file: {exc}") from exc
        return f"Saved to {target.relative_to(self.root)}"

    def list_dir(self, path: str | Path = ".") -> str:
        target = self.resolve(path)
        if not target.is_dir():
            raise SandboxError("not a directory")
        try:
            entries = []
            for item in target.iterdir():
                if item.is_symlink():
                    entries.append(item.name + " [symlink blocked]")
                else:
                    entries.append(item.name)
            return "\n".join(sorted(entries)) or "(empty)"
        except OSError as exc:
            raise SandboxError(f"could not list directory: {exc}") from exc


_sandbox: FileSandbox | None = None


def configure_sandbox(root: str | Path, max_read_bytes: int = 1048576) -> None:
    global _sandbox
    _sandbox = FileSandbox(root, max_read_bytes)


def _get() -> FileSandbox:
    if _sandbox is None:
        configure_sandbox(Path.cwd() / "workspace")
    assert _sandbox is not None
    return _sandbox


def read_file(path: str) -> str:
    try: return _get().read(path)
    except SandboxError as exc: return "Error: " + str(exc)


def write_file(path: str, content: str) -> str:
    try: return _get().write(path, content)
    except SandboxError as exc: return "Error: " + str(exc)


def list_dir(path: str = ".") -> str:
    try: return _get().list_dir(path)
    except SandboxError as exc: return "Error: " + str(exc)
