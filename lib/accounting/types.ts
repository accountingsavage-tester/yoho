export type AccountCategory =
  | "asset"
  | "contra_asset"
  | "liability"
  | "equity"
  | "contra_equity"
  | "revenue"
  | "expense";

export type NormalBalance = "debit" | "credit";
export type EntryKind = "regular" | "adjusting" | "closing";

export interface Account {
  id: string;
  code: string;
  name: string;
  category: AccountCategory;
  normalBalance: NormalBalance;
}

export interface JournalLine {
  accountId: string;
  debit: number;
  credit: number;
  memo?: string;
}

export interface JournalEntry {
  id: string;
  date: string;
  description: string;
  reference: string;
  kind: EntryKind;
  lines: JournalLine[];
}

export interface WorkspaceData {
  version: 1;
  business: string;
  periodEnd: string;
  accounts: Account[];
  entries: JournalEntry[];
}

export interface AccountBalance {
  accountId: string;
  debit: number;
  credit: number;
  balance: number;
}

export interface TrialBalance {
  rows: AccountBalance[];
  totalDebit: number;
  totalCredit: number;
  balanced: boolean;
}

export interface FinancialStatements {
  revenue: number;
  expenses: number;
  netIncome: number;
  assets: number;
  liabilities: number;
  contributedCapital: number;
  drawings: number;
  endingEquity: number;
  balanceSheetBalanced: boolean;
}
