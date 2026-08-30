import Link from "next/link";

export default function Landing(){
  return <main className="landing-shell">
    <div className="landing-orb orb-a"/><div className="landing-orb orb-b"/>
    <nav className="landing-nav glass"><div className="brand-mark"><span>AF</span><div><b>Auto Finance</b><small>Studio</small></div></div><Link className="nav-cta" href="/studio">Open Studio →</Link></nav>
    <section className="landing-hero">
      <div className="hero-copy"><div className="eyebrow">AI-ASSISTED ACCOUNTING WORKSPACE</div><h1>Turn accounting problems into <em>validated books.</em></h1><p>Upload a word problem, let the local LLM interpret the transactions, then let the deterministic accounting engine build and validate the journal, ledger, trial balance, and statements.</p><div className="hero-actions"><Link className="hero-primary" href="/studio">Launch Auto Solver</Link><Link className="hero-secondary" href="/studio">Explore the workspace</Link></div><div className="hero-proof"><span>Local WebLLM</span><span>Double-entry validation</span><span>Excel export</span></div></div>
      <div className="landing-preview glass"><div className="preview-bar"><span/><span/><span/><b>Auto Solver</b></div><div className="preview-status"><div><small>AI ENGINE</small><strong>Qwen 0.5B</strong></div><span className="status-dot"/> Ready</div><div className="preview-skeleton"><i/><i/><i/><i/></div><div className="preview-entry"><small>GENERATED JOURNAL</small><div><b>Cash</b><strong>₱50,000.00</strong></div><div><b>Owner's Capital</b><strong>₱50,000.00</strong></div><footer><span>Debit = Credit</span><b>Validated</b></footer></div></div>
    </section>
    <section className="landing-features"><article className="glass"><span className="feature-icon">01</span><h3>LLM interpretation</h3><p>Natural-language accounting problems are parsed into structured transactions and requested outputs.</p></article><article className="glass"><span className="feature-icon">02</span><h3>Deterministic math</h3><p>The ledger engine performs calculations and balance checks instead of trusting generated arithmetic.</p></article><article className="glass"><span className="feature-icon">03</span><h3>Interactive reports</h3><p>Move from entries to ledgers, trial balances, worksheets and financial statements in one workspace.</p></article></section>
    <footer className="landing-footer">Auto Finance Studio · AI-assisted accounting with transparent validation</footer>
  </main>
}