import { fastExtractTransactions, validateFastTransactions } from "./fast-solver";
import { normalizeSolverResult, type SolverResult } from "./v9-contracts";

export interface HybridCandidate { description: string; amount: number; debit: string; credit: string; confidence: number; rationale: string }
export interface HybridPlan { fast: HybridCandidate[]; needsLLM: boolean; coverage: number; warnings: string[] }

export function buildFastPlan(problem: string): HybridPlan {
  const fast = fastExtractTransactions(problem).map((x) => ({ description: x.description, amount: x.amount, debit: x.debit.account, credit: x.credit.account, confidence: x.confidence, rationale: x.rationale }));
  const validation = validateFastTransactions(fast.map((x) => ({ description: x.description, amount: x.amount, debit: { account: x.debit, type: "Asset" as const }, credit: { account: x.credit, type: "Asset" as const }, confidence: x.confidence, rationale: x.rationale })));
  const sentenceCount = Math.max(1, problem.split(/(?<=[.!?])\s+/).filter(Boolean).length);
  const coverage = Math.min(1, fast.length / sentenceCount);
  return { fast, needsLLM: !validation.valid || coverage < 0.9, coverage, warnings: validation.errors };
}

export function mergeHybrid(fast: HybridCandidate[], llm: unknown): SolverResult {
  const model = normalizeSolverResult(llm);
  const known = new Set(fast.map((x) => `${x.description}|${x.amount}`));
  const fastEntries = fast.map((x, i) => ({ id: `fast-${i}`, description: x.description, date: undefined, lines: [{ account: x.debit, debit: x.amount, credit: 0, memo: x.rationale }, { account: x.credit, debit: 0, credit: x.amount }] }));
  const llmEntries = model.entries.filter((entry) => !known.has(`${entry.description}|${entry.lines.reduce((s, x) => s + x.debit + x.credit, 0) / 2}`));
  return { ...model, entries: [...fastEntries, ...llmEntries], warnings: [...new Set([...model.warnings, ...(fast.length ? [] : ["No high-confidence deterministic transactions were found."])])] };
}
