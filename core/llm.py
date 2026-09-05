from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _model_args(model: str) -> list[str]:
    candidate = Path(model).expanduser()
    if candidate.suffix.lower() == ".gguf" or candidate.exists():
        return ["-m", str(candidate)]
    return ["-hf", model]


def run_llama(model: str, prompt: str, n: int = 200, context_size: int = 4096, timeout: int = 60) -> tuple[str, int, str]:
    executable = shutil.which("llama-cli")
    if executable is None:
        return "", 127, "llama-cli executable was not found. Install llama.cpp or configure its PATH."
    command = [executable, *_model_args(model), "-st", "-p", prompt, "-n", str(n), "-c", str(context_size), "--no-display-prompt"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "", 124, f"LLM generation timed out after {timeout} seconds."
    except OSError as exc:
        return "", 1, f"Could not start llama-cli: {exc}"
    if result.returncode != 0:
        return "", result.returncode, result.stderr.strip() or f"llama-cli exited with code {result.returncode}."
    lines = [line for line in result.stdout.strip().splitlines() if not line.startswith("[ Prompt:") and not line.startswith("[ Generation:")]
    return "\n".join(lines).strip(), 0, result.stderr.strip()


def check_llm(model: str) -> tuple[bool, str]:
    if shutil.which("llama-cli") is None:
        return False, "llama-cli executable was not found."
    if not isinstance(model, str) or not model.strip():
        return False, "No LLM model is configured."
    candidate = Path(model).expanduser()
    if (candidate.suffix.lower() == ".gguf" or "/" in model or "\\" in model) and not candidate.exists() and not model.startswith("unsloth/"):
        return False, f"Configured local model was not found: {candidate}"
    return True, "llama-cli available"
