# Yoho v8 Architecture

## Core rule

AI interprets accounting language. The deterministic accounting engine owns arithmetic, posting, balances, statements, and invariants.

## Layers

```text
Input documents / text
        |
        v
Document extraction
        |
        v
Problem analysis
        |
   +----+----+
   |         |
Fast rules  WebLLM
   |         |
   +----+----+
        |
        v
Strict AI contract
        |
        v
Accounting domain model
        |
        v
Deterministic accounting engine
        |
        +--> Journal / Ledger
        +--> Trial Balance
        +--> Adjustments
        +--> Worksheet
        +--> Financial Statements
        +--> Closing
        |
        v
Invariant validation
        |
        v
UI / export
```

## Domain rules

- Money is represented as numbers at the domain boundary and rounded to cents at deterministic calculation boundaries.
- Journal entries support any number of debit and credit lines.
- Contra-assets and contra-equity are explicit account categories.
- AI output is untrusted input and must pass runtime validation before entering the accounting engine.
- Financial statements are derived from journal data, never stored as authoritative state.
- Imported workbooks must eventually be grouped into complete journal entries before posting.
- Workspace data is versioned so future migrations can be deterministic.

## State ownership

React owns presentation state. The accounting engine owns accounting state transitions and calculations. Persistence is an adapter, not part of the accounting domain.

## Reliability target

Every accepted solution must satisfy:

1. Every entry balances.
2. Every referenced account exists.
3. No journal line has both debit and credit.
4. Trial balance balances.
5. Balance sheet balances.
6. Closing logic leaves temporary accounts at zero.
7. Post-closing trial balance contains permanent accounts only.

A model response that fails an invariant is not a valid accounting result.
