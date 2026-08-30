import type { Account, AccountBalance, FinancialStatements, JournalEntry, TrialBalance } from "./types";

export const CENTS = 100;
const cents = (value: number) => Number.isFinite(value) ? Math.round((value + Number.EPSILON) * CENTS) : 0;
const money = (value: number) => value / CENTS;

export function toCents(value: number): number { return cents(value); }
export function fromCents(value: number): number { return money(value); }
export function roundMoney(value: number): number { return money(cents(value)); }

export function entryTotals(entry: JournalEntry) {
  let debit = 0;
  let credit = 0;
  for (const line of entry.lines) {
    debit += Math.max(0, cents(line.debit));
    credit += Math.max(0, cents(line.credit));
  }
  return { debit: money(debit), credit: money(credit) };
}

export function calculateBalances(accounts: Account[], entries: JournalEntry[], includeClosing = false): AccountBalance[] {
  const totals = new Map<string, { debit: number; credit: number }>();
  for (const account of accounts) totals.set(account.id, { debit: 0, credit: 0 });
  for (const entry of entries) {
    if (!includeClosing && entry.kind === "closing") continue;
    for (const line of entry.lines) {
      const total = totals.get(line.accountId);
      if (!total) continue;
      total.debit += Math.max(0, cents(line.debit));
      total.credit += Math.max(0, cents(line.credit));
    }
  }
  return accounts.map((account) => {
    const total = totals.get(account.id) ?? { debit: 0, credit: 0 };
    const balance = account.normalBalance === "debit" ? total.debit - total.credit : total.credit - total.debit;
    return { accountId: account.id, debit: money(total.debit), credit: money(total.credit), balance: money(balance) };
  });
}

export function calculateTrialBalance(accounts: Account[], entries: JournalEntry[], includeClosing = false): TrialBalance {
  const rows = calculateBalances(accounts, entries, includeClosing);
  const totalDebit = rows.reduce((sum, row) => sum + cents(row.debit), 0);
  const totalCredit = rows.reduce((sum, row) => sum + cents(row.credit), 0);
  return { rows, totalDebit: money(totalDebit), totalCredit: money(totalCredit), balanced: totalDebit === totalCredit };
}

function statementAmount(account: Account, balance: number): number {
  return account.category === "contra_asset" || account.category === "contra_equity" ? -balance : balance;
}

export function calculateStatements(accounts: Account[], entries: JournalEntry[]): FinancialStatements {
  const trial = calculateTrialBalance(accounts, entries);
  const byId = new Map(trial.rows.map((row) => [row.accountId, row]));
  const amount = (category: Account["category"]) => money(accounts.filter((a) => a.category === category).reduce((sum, a) => sum + cents(statementAmount(a, byId.get(a.id)?.balance ?? 0)), 0));
  const revenue = amount("revenue");
  const expenses = amount("expense");
  const netIncome = roundMoney(revenue - expenses);
  const assets = roundMoney(amount("asset") + amount("contra_asset"));
  const liabilities = amount("liability");
  const contributedCapital = amount("equity");
  const drawings = amount("contra_equity");
  const endingEquity = roundMoney(contributedCapital + netIncome - drawings);
  return { revenue, expenses, netIncome, assets, liabilities, contributedCapital, drawings, endingEquity, balanceSheetBalanced: cents(assets) === cents(liabilities + endingEquity) };
}

export function isBalancedEntry(entry: JournalEntry): boolean {
  const totals = entryTotals(entry);
  return cents(totals.debit) === cents(totals.credit);
}

export function validateEntryShape(entry: JournalEntry): string[] {
  const errors: string[] = [];
  if (!entry.id.trim()) errors.push("Entry id is required.");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(entry.date) || Number.isNaN(Date.parse(entry.date))) errors.push("Entry date must be a valid YYYY-MM-DD date.");
  if (!entry.description.trim()) errors.push("Entry description is required.");
  if (entry.lines.length < 2) errors.push("A journal entry requires at least two lines.");
  for (const line of entry.lines) {
    if (!Number.isFinite(line.debit) || !Number.isFinite(line.credit)) errors.push("Journal amounts must be finite.");
    if (line.debit < 0 || line.credit < 0) errors.push("Journal amounts cannot be negative.");
    if (line.debit > 0 && line.credit > 0) errors.push("A journal line cannot contain both debit and credit.");
  }
  if (!isBalancedEntry(entry)) errors.push("Debits must equal credits.");
  return [...new Set(errors)];
}
