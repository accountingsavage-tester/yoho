# Auto Finance Studio v7

A browser-based accounting workspace with a local WebLLM interpretation layer and deterministic accounting calculations.

## Local model

The Auto Solver uses `@mlc-ai/web-llm` with `Qwen2.5-0.5B-Instruct-q4f16_1-MLC`. The model runs through WebGPU in the browser. No cloud AI API key is required. WebLLM reports initialization/download progress to the UI and the browser can cache model artifacts for later runs. A WebGPU-capable browser is required for local inference.

The model is used for natural-language extraction only. Journal calculations, validation, ledgers, trial balances, worksheets, and financial statements remain deterministic. If local inference is unavailable, the existing deterministic parser is used as a fallback.

## v7 features

- Required-output detection
- Complete accounting-cycle mode
- Local on-device WebLLM interpretation
- Model download progress
- TXT, DOCX, and text-PDF problem input
- Double-entry validation
- Editable multi-sheet XLSX export
- Mobile-oriented solver UI
