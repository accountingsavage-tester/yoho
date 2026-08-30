# Auto Finance Studio v7 - Local WebLLM

This build uses the official `@mlc-ai/web-llm` npm package and its smallest prebuilt Qwen model used by this app:

`Qwen2-0.5B-Instruct-q4f16_1-MLC`

## User flow

1. Open **Auto Solver**.
2. Press **Download & Initialize Local Model**.
3. WebLLM downloads the model and reports initialization progress.
4. The model is cached in the user's browser using IndexedDB.
5. Future visits can reuse the cached model.
6. Accounting problem interpretation runs locally through WebGPU.
7. Deterministic accounting rules validate and calculate the outputs.

Each user downloads and caches the model independently. The model is not bundled into the Vercel deployment and no API key is required.

## Requirements

- A secure web origin such as Vercel HTTPS.
- A browser/device with WebGPU support.
- Sufficient RAM/GPU memory for the selected model.

## Install

```bash
npm install
npm run build
```
