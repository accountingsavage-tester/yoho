import type { Account, AccountCategory, NormalBalance } from "./types";

export function normalBalanceFor(category: AccountCategory): NormalBalance {
  return category === "asset" || category === "contra_equity" || category === "expense"
    ? "debit"
    : "credit";
}

export function createAccount(
  id: string,
  code: string,
  name: string,
  category: AccountCategory,
): Account {
  return { id, code, name, category, normalBalance: normalBalanceFor(category) };
}

export const DEFAULT_ACCOUNTS: Account[] = [
  createAccount("101", "101", "Cash", "asset"),
  createAccount("102", "102", "Accounts Receivable", "asset"),
  createAccount("103", "103", "Supplies", "asset"),
  createAccount("104", "104", "Prepaid Rent", "asset"),
  createAccount("105", "105", "Equipment", "asset"),
  createAccount("106", "106", "Accumulated Depreciation—Equipment", "contra_asset"),
  createAccount("201", "201", "Accounts Payable", "liability"),
  createAccount("202", "202", "Unearned Revenue", "liability"),
  createAccount("203", "203", "Salaries Payable", "liability"),
  createAccount("204", "204", "Notes Payable", "liability"),
  createAccount("301", "301", "Owner's Capital", "equity"),
  createAccount("302", "302", "Owner's Drawing", "contra_equity"),
  createAccount("401", "401", "Service Revenue", "revenue"),
  createAccount("501", "501", "Rent Expense", "expense"),
  createAccount("502", "502", "Supplies Expense", "expense"),
  createAccount("503", "503", "Salaries Expense", "expense"),
  createAccount("504", "504", "Utilities Expense", "expense"),
  createAccount("505", "505", "Depreciation Expense", "expense"),
];
