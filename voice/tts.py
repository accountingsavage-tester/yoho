from __future__ import annotations

import shutil
import subprocess


def speak(text: str) -> str:
    executable = shutil.which("termux-tts-speak")
    if executable is None:
        return "TTS unavailable: termux-tts-speak is not installed."
    try:
        result = subprocess.run([executable, str(text)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "TTS timed out."
    except OSError as exc:
        return f"TTS error: {exc}"
    return "" if result.returncode == 0 else (result.stderr.strip() or "TTS command failed.")


def listen() -> str:
    executable = shutil.which("termux-speech-to-text")
    if executable is None:
        return "Speech-to-text unavailable: termux-speech-to-text is not installed."
    try:
        result = subprocess.run([executable], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "Speech-to-text timed out."
    except OSError as exc:
        return f"Speech-to-text error: {exc}"
    return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or "Speech-to-text command failed.")
