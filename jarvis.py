#!/usr/bin/env python3
"""JARVIS Termux CLI - PocketStrike-style multi-provider agent client."""
import json
import os
import sys
from typing import Any, Dict, List

import requests

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "qwen2.5:0.5b",
    "api_key": "",
}


def load_config() -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as exc:
            print(f"[config] Could not read config.json: {exc}")
    return cfg


def openai_compatible(cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
    base = cfg.get("base_url") or "https://api.openai.com/v1"
    base = base.rstrip("/")
    if not base.endswith("/v1") and cfg.get("provider") not in ("ollama",):
        base += "/v1"
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    payload = {
        "model": cfg.get("model"),
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }
    r = requests.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]


def anthropic(cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
    base = (cfg.get("base_url") or "https://api.anthropic.com/v1").rstrip("/")
    system = ""
    converted = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            converted.append(m)
    headers = {
        "content-type": "application/json",
        "x-api-key": cfg.get("api_key", ""),
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": cfg.get("model"),
        "max_tokens": 2048,
        "messages": converted,
    }
    if system:
        payload["system"] = system
    r = requests.post(f"{base}/messages", headers=headers, json=payload, timeout=180)
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def ask(cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
    provider = (cfg.get("provider") or "ollama").lower()
    if provider == "anthropic":
        return anthropic(cfg, messages)
    # Ollama's /v1 endpoint is OpenAI-compatible. Gemini/custom/OpenRouter/OpenAI
    # providers can use the same protocol when their base_url is configured.
    return openai_compatible(cfg, messages)


def main() -> None:
    cfg = load_config()
    provider = cfg.get("provider", "ollama")
    model = cfg.get("model", "qwen2.5:0.5b")
    print("JARVIS — Termux AI")
    print(f"Provider: {provider} | Model: {model}")
    print("Commands: /config, /clear, /exit")
    print()

    messages: List[Dict[str, str]] = [{
        "role": "system",
        "content": (
            "You are JARVIS, a concise technical AI assistant running in Termux. "
            "Answer directly. Do not claim to have executed commands unless a tool actually executed them."
        ),
    }]

    while True:
        try:
            user = input("JARVIS > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return
        if not user:
            continue
        if user == "/exit":
            return
        if user == "/clear":
            messages = messages[:1]
            print("Conversation cleared.")
            continue
        if user == "/config":
            print(json.dumps({k: ("********" if k == "api_key" and cfg.get(k) else v) for k, v in cfg.items()}, indent=2))
            continue

        messages.append({"role": "user", "content": user})
        try:
            answer = ask(cfg, messages)
            messages.append({"role": "assistant", "content": answer})
            print(f"\n{answer}\n")
        except requests.RequestException as exc:
            messages.pop()
            print(f"[API error] {exc}")
            if provider == "ollama":
                print("Check that Ollama is running and the model exists: ollama list")
        except Exception as exc:
            messages.pop()
            print(f"[error] {exc}")


if __name__ == "__main__":
    main()
