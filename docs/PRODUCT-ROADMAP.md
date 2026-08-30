# YOHO product architecture

## AI
- Local WebLLM is preferred only when a usable WebGPU adapter/device exists.
- WebLLM browser cache is the source of truth for model assets; UI state is persisted separately.
- AI output is an interpretation layer. Arithmetic and double-entry validation remain deterministic.
- Local and future cloud runtimes should expose the same completion interface.
- UI must explicitly show whether a solution was produced by Local WebLLM or another runtime.

## Workspace
- Persist active Studio section and draft solver/chat state locally.
- Prefer IndexedDB for larger accounting workspaces as the data model grows.
- Keep accounting records separate from transient AI state.

## UX
- Glassmorphism is used selectively for navigation, AI surfaces, and dashboards.
- Dense accounting tables remain high-contrast and readable.
- Every async surface needs loading, empty, success, and error states.
- Mobile is a first-class layout: touch targets, horizontal table scrolling, safe-area padding, and no hover-only controls.

## Validation
The deterministic engine must remain the authority for:
- debit/credit equality;
- account classification;
- trial balance equality;
- statement arithmetic;
- adjusting and closing mechanics.
