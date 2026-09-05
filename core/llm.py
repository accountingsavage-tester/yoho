from __future__ import annotations

import shutil
import subprocess


class LLMError(RuntimeError):
    pass


def run_llama(model: str, prompt: str, n: int = 200, context_size: int = 4096, timeout: int = 60) -> tuple[str, int, str]:
    executable = shutil.which("llama-cli")
    if executable is None:
        return "", 127, "llama-cli executable was not found. Install llama.cpp or configure its PATH."
    command = [executable, "-hf", model, "-st", "-p", prompt, "-n", str(n), "-c", str(context_size), "--no-display-prompt"]
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
    if not model or not isinstance(model, str):
        return False, "No LLM model is configured."
    return True, "llama-cli available"
