import type { Account, JournalEntry, WorkspaceData } from "./types";
import { calculateStatements, calculateTrialBalance, entryTotals, validateEntryShape } from "./engine";

export interface InvariantIssue { code: string; severity: "error" | "warning"; message: string; entryId?: string; accountId?: string }
export interface IntegrityReport { ok: boolean; errors: InvariantIssue[]; warnings: InvariantIssue[]; trialBalance: ReturnType<typeof calculateTrialBalance>; statements: ReturnType<typeof calculateStatements> }

export function validateWorkspace(workspace: WorkspaceData): IntegrityReport {
  const errors: InvariantIssue[] = [];
  const warnings: InvariantIssue[] = [];
  const accountIds = new Set<string>();
  const codes = new Set<string>();
  for (const account of workspace.accounts) {
    if (accountIds.has(account.id)) errors.push({ code: "DUPLICATE_ACCOUNT_ID", severity: "error", message: `Duplicate account id: ${account.id}`, accountId: account.id });
    accountIds.add(account.id);
    if (codes.has(account.code)) warnings.push({ code: "DUPLICATE_ACCOUNT_CODE", severity: "warning", message: `Duplicate account code: ${account.code}`, accountId: account.id });
    codes.add(account.code);
  }
  const entryIds = new Set<string>();
  for (const entry of workspace.entries) {
    if (entryIds.has(entry.id)) errors.push({ code: "DUPLICATE_ENTRY_ID", severity: "error", message: `Duplicate entry id: ${entry.id}`, entryId: entry.id });
    entryIds.add(entry.id);
    for (const line of entry.lines) {
      if (!accountIds.has(line.accountId)) errors.push({ code: "UNKNOWN_ACCOUNT", severity: "error", message: `Entry ${entry.id} references unknown account ${line.accountId}`, entryId: entry.id, accountId: line.accountId });
    }
    const shape = validateEntryShape(entry);
    for (const message of shape) errors.push({ code: "INVALID_ENTRY", severity: "error", message, entryId: entry.id });
  }
  const trialBalance = calculateTrialBalance(workspace.accounts, workspace.entries);
  if (!trialBalance.balanced) errors.push({ code: "TRIAL_BALANCE_UNBALANCED", severity: "error", message: `Trial balance is not balanced: ${trialBalance.totalDebit} Dr vs ${trialBalance.totalCredit} Cr.` });
  const statements = calculateStatements(workspace.accounts, workspace.entries);
  if (!statements.balanceSheetBalanced) errors.push({ code: "BALANCE_SHEET_UNBALANCED", severity: "error", message: "Assets do not equal liabilities plus ending equity." });
  return { ok: errors.length === 0, errors, warnings, trialBalance, statements };
}

export function validateCandidateEntry(entry: JournalEntry, accounts: Account[]): InvariantIssue[] {
  const issues: InvariantIssue[] = validateEntryShape(entry).map((message) => ({ code: "INVALID_ENTRY", severity: "error", message, entryId: entry.id }));
  const ids = new Set(accounts.map((a) => a.id));
  for (const line of entry.lines) if (!ids.has(line.accountId)) issues.push({ code: "UNKNOWN_ACCOUNT", severity: "error", message: `Unknown account ${line.accountId}.`, entryId: entry.id, accountId: line.accountId });
  const totals = entryTotals(entry);
  if (totals.debit !== totals.credit) issues.push({ code: "ENTRY_NOT_BALANCED", severity: "error", message: `Entry does not balance: ${totals.debit} Dr vs ${totals.credit} Cr.`, entryId: entry.id });
  return issues;
}
