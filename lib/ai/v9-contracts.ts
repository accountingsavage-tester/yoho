export const SOLVER_MODEL = "Qwen2-0.5B-Instruct-q4f16_1-MLC";
export const SOLVER_MAX_INPUT_CHARS = 9000;
export const SOLVER_MAX_OUTPUT_TOKENS = 384;

export interface SolverLine { account: string; debit: number; credit: number; memo?: string }
export interface SolverEntry { date?: string; description: string; lines: SolverLine[] }
export interface SolverResult {
  businessName?: string;
  periodEnd?: string;
  entries: SolverEntry[];
  adjustments: SolverEntry[];
  requestedOutputs: string[];
  assumptions: string[];
  warnings: string[];
}

const ALLOWED_OUTPUTS = new Set([
  "journal", "ledger", "trial_balance", "adjusted_trial_balance", "worksheet",
  "income_statement", "owner_equity", "balance_sheet", "closing_entries", "post_closing_trial_balance"
]);

function finiteMoney(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) / 100 : 0;
}

export function normalizeSolverResult(input: unknown): SolverResult {
  const value = (input && typeof input === "object") ? input as Record<string, unknown> : {};
  const normalizeEntry = (raw: unknown): SolverEntry | null => {
    if (!raw || typeof raw !== "object") return null;
    const r = raw as Record<string, unknown>;
    const lines = Array.isArray(r.lines) ? r.lines.map((line) => {
      const x = (line && typeof line === "object") ? line as Record<string, unknown> : {};
      return { account: String(x.account || "").trim(), debit: finiteMoney(x.debit), credit: finiteMoney(x.credit), memo: String(x.memo || "").trim() || undefined };
    }).filter((x) => x.account && (x.debit > 0 || x.credit > 0)) : [];
    if (!String(r.description || "").trim() || lines.length < 2) return null;
    return { date: String(r.date || "").trim() || undefined, description: String(r.description).trim(), lines };
  };
  const entries = Array.isArray(value.entries) ? value.entries.map(normalizeEntry).filter(Boolean) as SolverEntry[] : [];
  const adjustments = Array.isArray(value.adjustments) ? value.adjustments.map(normalizeEntry).filter(Boolean) as SolverEntry[] : [];
  const requestedOutputs = Array.isArray(value.requestedOutputs) ? value.requestedOutputs.map(String).filter((x) => ALLOWED_OUTPUTS.has(x)) : [];
  const assumptions = Array.isArray(value.assumptions) ? value.assumptions.map(String).slice(0, 12) : [];
  const warnings = Array.isArray(value.warnings) ? value.warnings.map(String).slice(0, 12) : [];
  return { businessName: String(value.businessName || "").trim() || undefined, periodEnd: String(value.periodEnd || "").trim() || undefined, entries, adjustments, requestedOutputs, assumptions, warnings };
}

export const SOLVER_SYSTEM = `Return ONLY compact JSON. Schema: {businessName,periodEnd,entries,adjustments,requestedOutputs,assumptions,warnings}. Each entry is {date,description,lines:[{account,debit,credit,memo}]}. Use plain numbers. Never put a value on both debit and credit. Never invent facts. requestedOutputs may contain only journal,ledger,trial_balance,adjusted_trial_balance,worksheet,income_statement,owner_equity,balance_sheet,closing_entries,post_closing_trial_balance. Keep explanations out of JSON. This is an accounting extraction task; calculations are performed by a deterministic engine.`;
