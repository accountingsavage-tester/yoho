import type { Account, JournalEntry, WorkspaceData } from "./types";
import { validateWorkspace } from "./validation";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function parseAccount(value: unknown): Account | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || typeof value.code !== "string" || typeof value.name !== "string") return null;
  if (!["asset", "contra_asset", "liability", "equity", "contra_equity", "revenue", "expense"].includes(String(value.category))) return null;
  if (value.normalBalance !== "debit" && value.normalBalance !== "credit") return null;
  return value as unknown as Account;
}

function parseEntry(value: unknown): JournalEntry | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== "string" || typeof value.date !== "string" || typeof value.description !== "string" || typeof value.reference !== "string") return null;
  if (!["regular", "adjusting", "closing"].includes(String(value.kind)) || !Array.isArray(value.lines)) return null;
  const lines = value.lines.map((line) => {
    if (!isRecord(line) || typeof line.accountId !== "string" || typeof line.debit !== "number" || typeof line.credit !== "number") return null;
    return line;
  });
  if (lines.some((line) => line === null)) return null;
  return { ...value, lines } as unknown as JournalEntry;
}

export function parseWorkspace(input: unknown): { ok: true; value: WorkspaceData } | { ok: false; errors: string[] } {
  if (!isRecord(input)) return { ok: false, errors: ["Workspace must be an object."] };
  if (input.version !== 1 || typeof input.business !== "string" || typeof input.periodEnd !== "string") {
    return { ok: false, errors: ["Unsupported or malformed workspace metadata."] };
  }
  if (!Array.isArray(input.accounts) || !Array.isArray(input.entries)) {
    return { ok: false, errors: ["Workspace requires accounts and entries arrays."] };
  }
  const accounts = input.accounts.map(parseAccount);
  const entries = input.entries.map(parseEntry);
  if (accounts.some((account) => account === null) || entries.some((entry) => entry === null)) {
    return { ok: false, errors: ["Workspace contains malformed accounts or journal entries."] };
  }
  const value = { version: 1 as const, business: input.business, periodEnd: input.periodEnd, accounts: accounts as Account[], entries: entries as JournalEntry[] };
  const issues = validateWorkspace(value).filter((issue) => issue.severity === "error");
  return issues.length ? { ok: false, errors: issues.map((issue) => issue.message) } : { ok: true, value };
}
