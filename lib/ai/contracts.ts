import type { AccountCategory, JournalEntry, JournalLine } from "../accounting/types";

export interface AITransaction {
  description: string;
  date?: string;
  lines: JournalLine[];
  confidence: number;
  rationale: string;
}

export interface AISolverResult {
  transactions: AITransaction[];
  requiredOutputs: string[];
  warnings: string[];
  confidence: number;
}

const categories = new Set<AccountCategory>([
  "asset", "contra_asset", "liability", "equity", "contra_equity", "revenue", "expense",
]);

const finiteNonNegative = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0;

export function validateAISolverResult(value: unknown): { ok: true; value: AISolverResult } | { ok: false; errors: string[] } {
  const errors: string[] = [];
  if (!value || typeof value !== "object" || Array.isArray(value)) return { ok: false, errors: ["AI result must be an object."] };
  const raw = value as Record<string, unknown>;
  if (!Array.isArray(raw.transactions)) errors.push("transactions must be an array.");
  if (!Array.isArray(raw.requiredOutputs)) errors.push("requiredOutputs must be an array.");
  if (!Array.isArray(raw.warnings)) errors.push("warnings must be an array.");
  if (!finiteNonNegative(raw.confidence) || Number(raw.confidence) > 1) errors.push("confidence must be between 0 and 1.");

  if (Array.isArray(raw.transactions)) {
    raw.transactions.forEach((transaction, index) => {
      if (!transaction || typeof transaction !== "object") { errors.push(`transactions[${index}] is invalid.`); return; }
      const t = transaction as Record<string, unknown>;
      if (typeof t.description !== "string" || !t.description.trim()) errors.push(`transactions[${index}] requires a description.`);
      if (!Array.isArray(t.lines) || t.lines.length < 2) errors.push(`transactions[${index}] requires at least two lines.`);
      if (!finiteNonNegative(t.confidence) || Number(t.confidence) > 1) errors.push(`transactions[${index}] confidence is invalid.`);
      if (typeof t.rationale !== "string") errors.push(`transactions[${index}] rationale is invalid.`);
      if (Array.isArray(t.lines)) t.lines.forEach((line, lineIndex) => {
        if (!line || typeof line !== "object") { errors.push(`transactions[${index}].lines[${lineIndex}] is invalid.`); return; }
        const l = line as Record<string, unknown>;
        if (typeof l.accountId !== "string" || !l.accountId) errors.push(`transactions[${index}].lines[${lineIndex}] accountId is invalid.`);
        if (!finiteNonNegative(l.debit) || !finiteNonNegative(l.credit)) errors.push(`transactions[${index}].lines[${lineIndex}] amount is invalid.`);
        if (finiteNonNegative(l.debit) && finiteNonNegative(l.credit) && l.debit > 0 && l.credit > 0) errors.push(`transactions[${index}].lines[${lineIndex}] has both debit and credit.`);
      });
    });
  }
  if (errors.length) return { ok: false, errors };
  return { ok: true, value: raw as unknown as AISolverResult };
}

export function transactionToEntry(transaction: AITransaction, id: string, date: string): JournalEntry {
  return {
    id,
    date: transaction.date || date,
    description: transaction.description,
    reference: "AI",
    kind: "regular",
    lines: transaction.lines,
  };
}
