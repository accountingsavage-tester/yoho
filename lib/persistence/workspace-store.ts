import type { WorkspaceData } from "../accounting/types";
import { parseWorkspace } from "../accounting/schema";

export const WORKSPACE_STORAGE_KEY = "yoho:workspace:v3";

export function loadWorkspace(): WorkspaceData | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(WORKSPACE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = parseWorkspace(JSON.parse(raw));
    return parsed.ok ? parsed.value : null;
  } catch {
    return null;
  }
}

export function saveWorkspace(workspace: WorkspaceData): boolean {
  if (typeof window === "undefined") return false;
  try {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(workspace));
    return true;
  } catch {
    return false;
  }
}

export function clearWorkspace(): void {
  if (typeof window === "undefined") return;
  try { localStorage.removeItem(WORKSPACE_STORAGE_KEY); } catch {}
}
