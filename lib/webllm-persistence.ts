export const WEBLLM_STATE_KEY = "yoho:webllm:download-state:v3";
const DB_NAME = "yoho-device-memory";
const DB_VERSION = 1;
const STORE_NAME = "runtime";
const WRITE_THROTTLE_MS = 750;

export type WebLLMDownloadState = {
  modelId: string;
  status: "idle" | "downloading" | "ready" | "error";
  progress: number;
  text: string;
  updatedAt: number;
};

let pendingState: WebLLMDownloadState | null = null;
let writeTimer: ReturnType<typeof setTimeout> | null = null;

function writeLocal(state: WebLLMDownloadState) {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(WEBLLM_STATE_KEY, JSON.stringify(state)); } catch {}
}

function openDb(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) request.result.createObjectStore(STORE_NAME);
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
    } catch { resolve(null); }
  });
}

async function mirrorToIndexedDB(state: WebLLMDownloadState) {
  const db = await openDb();
  if (!db) return;
  try {
    await new Promise<void>((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      tx.objectStore(STORE_NAME).put(state, WEBLLM_STATE_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
      tx.onabort = () => resolve();
    });
  } finally { db.close(); }
}

export function loadWebLLMState(modelId: string): WebLLMDownloadState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(WEBLLM_STATE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as WebLLMDownloadState;
    return value?.modelId === modelId ? value : null;
  } catch { return null; }
}

export function saveWebLLMState(state: WebLLMDownloadState) {
  if (typeof window === "undefined") return;
  pendingState = state;

  // Progress callbacks can fire many times per second. Writing localStorage on
  // every callback can itself cause main-thread jank, so coalesce progress writes.
  const immediate = state.status === "ready" || state.status === "error";
  if (immediate) {
    if (writeTimer) clearTimeout(writeTimer);
    writeTimer = null;
    writeLocal(state);
    void mirrorToIndexedDB(state);
    return;
  }

  if (writeTimer) return;
  writeTimer = setTimeout(() => {
    writeTimer = null;
    if (pendingState) {
      writeLocal(pendingState);
      void mirrorToIndexedDB(pendingState);
    }
  }, WRITE_THROTTLE_MS);
}

export async function loadWebLLMStateFromDevice(modelId: string): Promise<WebLLMDownloadState | null> {
  const local = loadWebLLMState(modelId);
  const db = await openDb();
  if (!db) return local;
  try {
    const value = await new Promise<WebLLMDownloadState | null>((resolve) => {
      const request = db.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(WEBLLM_STATE_KEY);
      request.onsuccess = () => resolve((request.result as WebLLMDownloadState | undefined) || null);
      request.onerror = () => resolve(null);
    });
    if (value?.modelId === modelId && (!local || value.updatedAt > local.updatedAt)) {
      writeLocal(value);
      return value;
    }
    return local;
  } finally { db.close(); }
}

export function clearWebLLMState() {
  if (typeof window === "undefined") return;
  try { localStorage.removeItem(WEBLLM_STATE_KEY); } catch {}
  void openDb().then((db) => {
    if (!db) return;
    try { db.transaction(STORE_NAME, "readwrite").objectStore(STORE_NAME).delete(WEBLLM_STATE_KEY); } finally { db.close(); }
  });
}

export async function requestPersistentBrowserStorage() {
  if (typeof navigator === "undefined" || !navigator.storage?.persist) return false;
  try { return await navigator.storage.persist(); } catch { return false; }
}

export async function isPersistentBrowserStorage() {
  if (typeof navigator === "undefined" || !navigator.storage?.persisted) return false;
  try { return await navigator.storage.persisted(); } catch { return false; }
}
