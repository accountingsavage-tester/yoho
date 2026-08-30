import { calculateStatements, calculateTrialBalance, entryTotals } from "./engine";
import type { Account, JournalEntry, WorkspaceData } from "./types";

export interface ValidationIssue {
  code: string;
  message: string;
  severity: "error" | "warning";
  entryId?: string;
  accountId?: string;
}

export function validateEntry(entry: JournalEntry, accounts: Account[]): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const known = new Set(accounts.map((account) => account.id));
  const totals = entryTotals(entry);

  if (!entry.id || !entry.date || !entry.description.trim()) {
    issues.push({ code: "ENTRY_METADATA", severity: "error", message: "Entry requires an id, date, and description.", entryId: entry.id });
  }
  if (entry.lines.length < 2) {
    issues.push({ code: "ENTRY_LINES", severity: "error", message: "A journal entry must contain at least two lines.", entryId: entry.id });
  }
  if (Math.abs(totals.debit - totals.credit) >= 0.005) {
    issues.push({ code: "ENTRY_UNBALANCED", severity: "error", message: `Debits (${totals.debit}) do not equal credits (${totals.credit}).`, entryId: entry.id });
  }

  for (const line of entry.lines) {
    if (!known.has(line.accountId)) {
      issues.push({ code: "UNKNOWN_ACCOUNT", severity: "error", message: `Unknown account ${line.accountId}.`, entryId: entry.id, accountId: line.accountId });
    }
    if (!Number.isFinite(line.debit) || !Number.isFinite(line.credit) || line.debit < 0 || line.credit < 0) {
      issues.push({ code: "INVALID_AMOUNT", severity: "error", message: "Journal amounts must be finite and non-negative.", entryId: entry.id, accountId: line.accountId });
    }
    if (line.debit > 0 && line.credit > 0) {
      issues.push({ code: "BOTH_SIDES", severity: "error", message: "A journal line cannot contain both a debit and a credit.", entryId: entry.id, accountId: line.accountId });
    }
  }
  return issues;
}

export function validateWorkspace(workspace: WorkspaceData): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const ids = new Set<string>();
  const codes = new Set<string>();

  for (const account of workspace.accounts) {
    if (ids.has(account.id)) issues.push({ code: "DUPLICATE_ACCOUNT_ID", severity: "error", message: `Duplicate account id ${account.id}.`, accountId: account.id });
    ids.add(account.id);
    if (codes.has(account.code)) issues.push({ code: "DUPLICATE_ACCOUNT_CODE", severity: "warning", message: `Duplicate account code ${account.code}.`, accountId: account.id });
    codes.add(account.code);
  }

  for (const entry of workspace.entries) issues.push(...validateEntry(entry, workspace.accounts));

  const trial = calculateTrialBalance(workspace.accounts, workspace.entries);
  if (!trial.balanced) {
    issues.push({ code: "TRIAL_BALANCE_UNBALANCED", severity: "error", message: `Trial balance is out of balance by ${Math.abs(trial.totalDebit - trial.totalCredit).toFixed(2)}.` });
  }

  const statements = calculateStatements(workspace.accounts, workspace.entries);
  if (!statements.balanceSheetBalanced) {
    issues.push({ code: "BALANCE_SHEET_UNBALANCED", severity: "error", message: `Balance sheet does not balance: assets ${statements.assets} versus liabilities plus equity ${statements.liabilities + statements.endingEquity}.` });
  }
  return issues;
}
