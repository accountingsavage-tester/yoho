# JARVIS for Android Termux

A local-first JARVIS assistant designed for Android + Termux. GitHub is the canonical codebase; the model runs locally through `llama-cli` and Android automation uses ADB or Termux:API.

## Requirements

- Android phone with Termux
- Python 3.10+ recommended
- Git
- `adb` from Termux's `android-tools` package when Android UI control is needed
- `llama-cli` available in `PATH` for local LLM chat
- Termux:API app plus the `termux-api` package for battery, TTS, flashlight, clipboard, camera, Wi-Fi, and related phone tools

Jarvis does not require root, Docker, systemd, `/usr/bin`, or desktop Linux services.

## Install in Termux

```sh
pkg update
pkg upgrade
pkg install python git android-tools

git clone https://github.com/accountingsavage-tester/yoho.git
cd yoho

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

If virtual environments are not practical on your Termux installation, the project uses only Python's standard library at runtime, so `pip install -r requirements.txt` installs no runtime packages.

Create the workspace:

```sh
mkdir -p workspace data
```

## Termux:API

Install the Termux:API Android companion app from a trusted source, then in Termux install its command package:

```sh
pkg install termux-api
```

Verify with:

```sh
termux-battery-status
termux-tts-speak "JARVIS online"
```

Android will ask for permissions when a specific API needs them.

## ADB setup

Check ADB:

```sh
adb devices
```

The configuration defaults to the first/default ADB device when `adb_serial` is `null`. To pin a device, set its serial in `config.json`:

```json
"adb_serial": "SERIAL_HERE"
```

Jarvis reports ADB availability at startup. Chat does not require ADB; `/control` does.

## Local LLM

Jarvis calls `llama-cli` locally. It does not silently download a large model. Make sure `llama-cli` is in `PATH`, or install/build llama.cpp separately for your Termux environment.

The default model configuration is:

```json
"model": "unsloth/SmolLM2-360M-Instruct-GGUF:Q4_K_M"
```

For a local GGUF file, configure the model value and adjust `core/llm.py` only if your llama.cpp invocation requires a different local-model flag. Never commit GGUF/model files to Git.

## Configuration

Important settings in `config.json`:

- `model`: local/Hugging Face llama.cpp model identifier
- `adb_serial`: `null` for the default device
- `context_size`: llama context size
- `max_tokens`: chat generation limit
- `llm_timeout`: maximum seconds per LLM subprocess
- `workspace_path`: filesystem workspace, restricted to this repository
- `max_file_read_bytes`: maximum file size loaded through `/read`
- `max_context_messages`: maximum conversation messages retained
- `memory.db_path`: SQLite memory database

## Run

```sh
python jarvis.py
```

Startup checks report Python, workspace, ADB, LLM, and memory status.

## Commands

```text
/help
/diagnostics
/control <goal>
/read <path>
/write <path> <content>
/ls [path]
/time
/battery
/calc <expression>
```

Natural-language Android controls include battery, flashlight, vibration, clipboard, notifications, Wi-Fi, location, camera, app launching, URLs, Home, Back, and volume when the corresponding Termux/Android capability is available.

## Filesystem security

`/read`, `/write`, and `/ls` are restricted to `workspace/` by default. Paths are resolved with `pathlib`, traversal outside the workspace is rejected, symlink escapes are rejected, and `/read` enforces `max_file_read_bytes`.

The LLM never receives arbitrary shell access. Model-generated Android actions are parsed and validated before execution.

## Android control security

`/control` follows this pipeline:

1. ADB dumps the current UI hierarchy.
2. Jarvis extracts validated visible elements and their properties.
3. The local LLM chooses one action by element index.
4. Python validates the action and the selected element.
5. Only the fixed Android operation is executed.

The model cannot supply arbitrary shell commands or raw coordinates.

## Testing

```sh
python -m pytest -q
python -m compileall .
```

The test suite mocks LLM/ADB subprocesses and does not require Android hardware, ADB connectivity, or a model.

## Smoke test

```sh
python -m pytest -q
python jarvis.py
```

Then try:

```text
/help
/ls
/time
/calc 2 + 2
```

With Android access available:

```text
/battery
/control open settings
```

## Troubleshooting

**`llama-cli executable was not found`**: install/configure llama.cpp and ensure `llama-cli` is on `PATH`.

**`ADB executable was not found`**: install `android-tools`.

**`No Android device is connected`**: run `adb devices` and complete Android debugging/pairing.

**Termux API command missing**: install `termux-api` and the Termux:API companion app.

**Workspace error**: keep `workspace_path` inside the repository. Do not point it at `/sdcard`, `/`, or another unrestricted directory.

## Project structure

```text
jarvis.py
config.json
core/
  context.py
  llm.py
  router.py
memory/
  memory.py
tools/
  files.py
  phone.py
  system.py
  utility.py
voice/
  tts.py
models/
tests/
requirements.txt
requirements-dev.txt
.github/workflows/ci.yml
```

## Offline model note

Internet access is not required while Jarvis is running if the configured model is already available to `llama-cli`. The default `-hf` model identifier may require network access the first time llama.cpp obtains the model. For fully offline operation, preinstall the model and configure the local model path according to your llama.cpp build.
