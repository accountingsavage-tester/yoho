import type {
  Account,
  AccountBalance,
  FinancialStatements,
  JournalEntry,
  TrialBalance,
} from "./types";

export const CENT = 100;
const round = (value: number) => Math.round((value + Number.EPSILON) * CENT) / CENT;

export function entryTotals(entry: JournalEntry) {
  return entry.lines.reduce(
    (totals, line) => ({
      debit: round(totals.debit + Math.max(0, line.debit)),
      credit: round(totals.credit + Math.max(0, line.credit)),
    }),
    { debit: 0, credit: 0 },
  );
}

export function calculateBalances(
  accounts: Account[],
  entries: JournalEntry[],
  includeClosing = false,
): AccountBalance[] {
  const totals = new Map<string, { debit: number; credit: number }>();
  for (const account of accounts) totals.set(account.id, { debit: 0, credit: 0 });

  for (const entry of entries) {
    if (!includeClosing && entry.kind === "closing") continue;
    for (const line of entry.lines) {
      const current = totals.get(line.accountId);
      if (!current) continue;
      current.debit = round(current.debit + Math.max(0, line.debit));
      current.credit = round(current.credit + Math.max(0, line.credit));
    }
  }

  return accounts.map((account) => {
    const value = totals.get(account.id) ?? { debit: 0, credit: 0 };
    const balance = account.normalBalance === "debit"
      ? round(value.debit - value.credit)
      : round(value.credit - value.debit);
    return { accountId: account.id, ...value, balance };
  });
}

export function calculateTrialBalance(
  accounts: Account[],
  entries: JournalEntry[],
  includeClosing = false,
): TrialBalance {
  const rows = calculateBalances(accounts, entries, includeClosing);
  const totalDebit = round(rows.reduce((sum, row) => sum + row.debit, 0));
  const totalCredit = round(rows.reduce((sum, row) => sum + row.credit, 0));
  return {
    rows,
    totalDebit,
    totalCredit,
    balanced: Math.abs(totalDebit - totalCredit) < 0.005,
  };
}

export function calculateStatements(
  accounts: Account[],
  entries: JournalEntry[],
): FinancialStatements {
  const trial = calculateTrialBalance(accounts, entries);
  const byId = new Map(trial.rows.map((row) => [row.accountId, row]));
  const amount = (category: Account["category"]) => round(
    accounts
      .filter((account) => account.category === category)
      .reduce((sum, account) => sum + (byId.get(account.id)?.balance ?? 0), 0),
  );

  const revenue = amount("revenue");
  const expenses = amount("expense");
  const netIncome = round(revenue - expenses);
  const assets = round(amount("asset") + amount("contra_asset"));
  const liabilities = amount("liability");
  const contributedCapital = amount("equity");
  const drawings = amount("contra_equity");
  const endingEquity = round(contributedCapital + netIncome - drawings);

  return {
    revenue,
    expenses,
    netIncome,
    assets,
    liabilities,
    contributedCapital,
    drawings,
    endingEquity,
    balanceSheetBalanced: Math.abs(assets - (liabilities + endingEquity)) < 0.005,
  };
}

export function isBalancedEntry(entry: JournalEntry): boolean {
  const totals = entryTotals(entry);
  return Math.abs(totals.debit - totals.credit) < 0.005;
}
