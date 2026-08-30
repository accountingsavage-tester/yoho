export const WEBLLM_STATE_KEY = "yoho:webllm:download-state:v1";

export type WebLLMDownloadState = {
  modelId: string;
  status: "idle" | "downloading" | "ready" | "error";
  progress: number;
  text: string;
  updatedAt: number;
};

export function loadWebLLMState(modelId: string): WebLLMDownloadState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(WEBLLM_STATE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as WebLLMDownloadState;
    return value?.modelId === modelId ? value : null;
  } catch {
    return null;
  }
}

export function saveWebLLMState(state: WebLLMDownloadState) {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(WEBLLM_STATE_KEY, JSON.stringify(state)); } catch {}
}

export function clearWebLLMState() {
  if (typeof window === "undefined") return;
  try { localStorage.removeItem(WEBLLM_STATE_KEY); } catch {}
}
