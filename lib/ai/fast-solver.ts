export type FastAccountType = "Asset" | "Liability" | "Equity" | "Revenue" | "Expense";
export type FastTransaction = {
  description: string;
  amount: number;
  debit: { account: string; type: FastAccountType };
  credit: { account: string; type: FastAccountType };
  confidence: number;
  rationale: string;
};

const money = (s: string) => {
  const cleaned = s.replace(/,/g, "").replace(/₱|php|peso/gi, "").trim();
  const k = /k$/i.test(cleaned) ? 1000 : 1;
  const n = Number(cleaned.replace(/k$/i, ""));
  return Number.isFinite(n) ? Math.round(n * k * 100) / 100 : 0;
};

const amountFrom = (text: string) => {
  const m = text.match(/(?:₱|php|p)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?/i);
  return m ? money(`${m[1]}${m[2] || ""}`) : 0;
};

const make = (description: string, amount: number, debit: string, debitType: FastAccountType, credit: string, creditType: FastAccountType, rationale: string): FastTransaction => ({
  description, amount, debit: { account: debit, type: debitType }, credit: { account: credit, type: creditType }, confidence: 0.96, rationale,
});

/**
 * Fast deterministic pass for common accounting events. It intentionally does not
 * replace the LLM; it handles high-confidence patterns without spending model tokens.
 */
export function fastExtractTransactions(input: string): FastTransaction[] {
  const out: FastTransaction[] = [];
  const chunks = input.split(/(?<=[.!?])\s+(?=[A-Z₱])/).filter(Boolean);
  for (const raw of chunks) {
    const t = raw.trim();
    const amount = amountFrom(t);
    if (!amount) continue;
    const l = t.toLowerCase();

    if (/consult|provided .*service|performed .*service|service .*and .*received|service .*for .*and .*paid/i.test(t) && /cash|right away|received|got .*cash|paid .*right away/i.test(t)) {
      out.push(make(t, amount, "Cash", "Asset", "Service Revenue", "Revenue", "Cash was received for services, increasing an asset and revenue."));
      continue;
    }
    if (/consult|provided .*service|performed .*service|service/i.test(t) && /pay next|later|on account|receivable|will pay/i.test(t)) {
      out.push(make(t, amount, "Accounts Receivable", "Asset", "Service Revenue", "Revenue", "Services were earned but payment is deferred, creating a receivable."));
      continue;
    }
    if (/bought|purchased|acquired/i.test(t) && /laptop|computer|equipment|machine/i.test(t) && /cash|paid/i.test(t)) {
      out.push(make(t, amount, "Equipment", "Asset", "Cash", "Asset", "Equipment increased while cash decreased."));
      continue;
    }
    if (/rent/i.test(t) && /paid/i.test(t)) {
      out.push(make(t, amount, "Rent Expense", "Expense", "Cash", "Asset", "Current-period rent is an expense paid in cash."));
      continue;
    }
    if (/electric|utilities|internet/i.test(t) && /paid/i.test(t)) {
      out.push(make(t, amount, "Utilities Expense", "Expense", "Cash", "Asset", "Utilities were consumed and paid in cash."));
      continue;
    }
    if (/supplies/i.test(t) && /on account/i.test(t)) {
      out.push(make(t, amount, "Supplies", "Asset", "Accounts Payable", "Liability", "Supplies were acquired and payment is owed to the supplier."));
      continue;
    }
    if (/paid .*toward|payment .*toward|paid .*owed/i.test(t) && /supplier|officehub|account payable|owed/i.test(t)) {
      out.push(make(t, amount, "Accounts Payable", "Liability", "Cash", "Asset", "A payment reduces the payable and cash."));
      continue;
    }
    if (/withdraw|personal use|owner.*took|drew/i.test(l)) {
      out.push(make(t, amount, "Owner's Drawing", "Equity", "Cash", "Asset", "An owner withdrawal reduces equity and cash."));
      continue;
    }
    if (/employee|salary|wage/i.test(t) && /owe|unpaid|hasn't been paid|not paid/i.test(t)) {
      out.push(make(t, amount, "Salaries Expense", "Expense", "Salaries Payable", "Liability", "Work was incurred but remains unpaid, creating an accrued liability."));
      continue;
    }
  }
  return out;
}

export function validateFastTransactions(items: FastTransaction[]) {
  const errors: string[] = [];
  for (const x of items) {
    if (!x.amount || x.amount <= 0) errors.push(`Invalid amount for ${x.description}`);
    if (!x.debit.account || !x.credit.account) errors.push(`Incomplete accounts for ${x.description}`);
    if (x.debit.account === x.credit.account) errors.push(`Same account on both sides for ${x.description}`);
  }
  return { valid: errors.length === 0, errors };
}
