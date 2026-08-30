"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CreateWebWorkerMLCEngine } from "@mlc-ai/web-llm";
import { loadWebLLMState, requestPersistentBrowserStorage, saveWebLLMState } from "../../lib/webllm-persistence";

const MODEL = "Qwen2-0.5B-Instruct-q4f16_1-MLC";
const MAX_SOLVER_TOKENS = 512;
const MAX_CHAT_TOKENS = 160;
const MAX_CHAT_MESSAGES = 4;
const MAX_CONTEXT_CHARS = 6000;

type Status = "idle" | "checking" | "loading" | "ready" | "error";
type JournalLine = { account: string; debit: number; credit: number; explanation: string };
type Solution = { businessName?: string; analysis: string; assumptions: string[]; journal: JournalLine[]; checks: string[]; outputs: string[] };
type ChatMessage = { role: "user" | "assistant"; text: string };
type TraceItem = { label: string; detail: string; state: "pending" | "active" | "done" };

const money = (n: number) => new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(n || 0);

function extractJson(text: string) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  const candidate = fenced?.[1] || text.match(/\{[\s\S]*\}/)?.[0];
  if (!candidate) throw new Error("The model did not return structured accounting data.");
  return JSON.parse(candidate);
}

const SYSTEM = `You are an accounting reasoning assistant. Return ONLY JSON: {"businessName":"","analysis":"","assumptions":[],"journal":[{"account":"","debit":0,"credit":0,"explanation":""}],"checks":[],"outputs":[]}. Detect the business/company name if explicitly stated in the problem; otherwise use an empty string. Use standard double-entry rules. Do not invent facts. State assumptions. Journal must balance. Numbers must be plain numbers. Keep analysis concise and explain the accounting rationale, not hidden chain-of-thought.`;
const CHAT_SYSTEM = `You are a concise accounting tutor. Explain debit/credit logic and accounting concepts accurately. Use short answers unless detail is requested. Do not fabricate facts. If current solver context is supplied, use it.`;

const TRACE: TraceItem[] = [
  { label: "Problem understood", detail: "Reading the accounting period, entities, and requested outputs.", state: "pending" },
  { label: "Transactions identified", detail: "Extracting economic events and amounts.", state: "pending" },
  { label: "Accounts classified", detail: "Mapping events to appropriate account types.", state: "pending" },
  { label: "Debit / credit treatment", detail: "Applying double-entry accounting rules.", state: "pending" },
  { label: "Journal constructed", detail: "Building structured journal lines from the analysis.", state: "pending" },
  { label: "Accounting validation", detail: "Checking that the proposed entry balances.", state: "pending" },
];

export default function AIWorkbench() {
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("Local model not initialized");
  const [engine, setEngine] = useState<any>(null);
  const [gpuInfo, setGpuInfo] = useState("Not checked");
  const [storageInfo, setStorageInfo] = useState("Browser storage not checked");
  const [problem, setProblem] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyStage, setBusyStage] = useState("");
  const [trace, setTrace] = useState<TraceItem[]>(TRACE);
  const [error, setError] = useState("");
  const initializing = useRef(false);
  const workerRef = useRef<Worker | null>(null);

  const total = useMemo(() => solution?.journal.reduce((a, x) => ({ debit: a.debit + Number(x.debit || 0), credit: a.credit + Number(x.credit || 0) }), { debit: 0, credit: 0 }) || { debit: 0, credit: 0 }, [solution]);

  const updateTrace = (activeIndex: number) => setTrace(TRACE.map((item, index) => ({ ...item, state: index < activeIndex ? "done" : index === activeIndex ? "active" : "pending" })));

  async function initialize(auto = false) {
    if (initializing.current || engine || status === "ready") return;
    initializing.current = true;
    setStatus("checking"); setError(""); setStatusText(auto ? "Restoring local model…" : "Checking browser GPU support…");
    try {
      const previous = loadWebLLMState(MODEL);
      if (previous) {
        setProgress(previous.progress);
        if (previous.status === "downloading") setStatusText(`Reusing cached model assets from ${previous.progress}%…`);
        if (previous.status === "ready") setStatusText("Restoring cached model…");
      }
      const gpu = (navigator as any).gpu;
      if (!gpu) throw new Error("This browser does not expose WebGPU. Local WebLLM is unavailable on this device.");
      const adapter = await gpu.requestAdapter({ powerPreference: "low-power" });
      if (!adapter) throw new Error("No compatible GPU adapter was found. Use a device with WebGPU support or a cloud AI runtime.");
      setGpuInfo("WebGPU adapter detected");
      const persistent = await requestPersistentBrowserStorage();
      setStorageInfo(persistent ? "Persistent storage enabled" : "Browser storage available");
      setStatus("loading");
      saveWebLLMState({ modelId: MODEL, status: "downloading", progress: previous?.progress || 0, text: "Initializing WebLLM", updatedAt: Date.now() });
      if (!workerRef.current) workerRef.current = new Worker(new URL("./webllm.worker.ts", import.meta.url), { type: "module" });
      const next = await CreateWebWorkerMLCEngine(workerRef.current, MODEL, {
        initProgressCallback: (p: any) => {
          const value = Math.max(0, Math.min(100, Math.round((p?.progress || 0) * 100)));
          setProgress(value);
          setStatusText(p?.text || `Preparing model… ${value}%`);
          saveWebLLMState({ modelId: MODEL, status: value >= 100 ? "ready" : "downloading", progress: value, text: p?.text || "Preparing model", updatedAt: Date.now() });
        },
      });
      setEngine(next);
      setStatus("ready"); setProgress(100); setStatusText("Local LLM ready — worker inference enabled");
      saveWebLLMState({ modelId: MODEL, status: "ready", progress: 100, text: "Local LLM ready", updatedAt: Date.now() });
    } catch (e: any) {
      const message = e?.message || "WebLLM initialization failed.";
      setGpuInfo(message.toLowerCase().includes("gpu") || message.toLowerCase().includes("webgpu") ? "No compatible GPU adapter" : gpuInfo);
      setStatus("error"); setStatusText("Local LLM could not start"); setError(message);
      saveWebLLMState({ modelId: MODEL, status: "error", progress, text: message, updatedAt: Date.now() });
    } finally { initializing.current = false; }
  }

  useEffect(() => {
    const saved = loadWebLLMState(MODEL);
    if (saved) {
      setProgress(saved.progress);
      setStatusText(saved.status === "ready" ? "Cached model found — restoring…" : saved.status === "downloading" ? `Cached assets found — resuming from ${saved.progress}%…` : saved.text);
    }
    void initialize(true);
    return () => { workerRef.current?.terminate(); workerRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function complete(messages: any[], temperature = 0.1, maxTokens = MAX_SOLVER_TOKENS) {
    if (!engine) throw new Error("Initialize the local model first.");
    const compact = messages.map((m) => ({ ...m, content: String(m.content).slice(-MAX_CONTEXT_CHARS) }));
    const result = await engine.chat.completions.create({ messages: compact, temperature, max_tokens: maxTokens });
    return result?.choices?.[0]?.message?.content || "";
  }

  async function solve() {
    if (!problem.trim()) return setError("Enter an accounting problem first.");
    setBusy(true); setError(""); setSolution(null); setTrace(TRACE.map((x) => ({ ...x, state: "pending" })));
    try {
      updateTrace(0); setBusyStage("Understanding the problem…");
      await new Promise((r) => setTimeout(r, 50));
      updateTrace(1); setBusyStage("Identifying transactions and amounts…");
      await new Promise((r) => setTimeout(r, 50));
      updateTrace(2); setBusyStage("Classifying accounts…");
      const raw = await complete([{ role: "system", content: SYSTEM }, { role: "user", content: `Solve this accounting problem:\n\n${problem.trim()}` }], 0.05, MAX_SOLVER_TOKENS);
      updateTrace(3); setBusyStage("Determining debit and credit treatment…");
      await new Promise((r) => setTimeout(r, 40));
      const parsed = extractJson(raw) as Solution;
      if (!Array.isArray(parsed.journal)) throw new Error("Invalid journal returned by model.");
      updateTrace(4); setBusyStage("Building the journal entry…");
      await new Promise((r) => setTimeout(r, 40));
      const debit = parsed.journal.reduce((s, x) => s + Number(x.debit || 0), 0);
      const credit = parsed.journal.reduce((s, x) => s + Number(x.credit || 0), 0);
      updateTrace(5); setBusyStage("Validating that debits equal credits…");
      await new Promise((r) => setTimeout(r, 40));
      if (Math.abs(debit - credit) > 0.005) throw new Error(`Model returned an unbalanced entry (${money(debit)} Dr vs ${money(credit)} Cr).`);
      setBusyStage("Preparing validated output…");
      setTrace(TRACE.map((x) => ({ ...x, state: "done" })));
      setSolution({ ...parsed, businessName: parsed.businessName?.trim() || "" });
    } catch (e: any) { setError(e?.message || "The accounting problem could not be solved."); }
    finally { setBusy(false); setBusyStage(""); }
  }

  async function sendChat() {
    if (!chatInput.trim() || busy) return;
    const text = chatInput.trim(); setChatInput(""); setError("");
    const next = [...chat, { role: "user" as const, text }].slice(-MAX_CHAT_MESSAGES);
    setChat(next); setBusy(true); setBusyStage("Generating a concise response…");
    try {
      const context = solution ? `Current solver context: Business: ${solution.businessName || "not detected"}. Analysis: ${solution.analysis}. Journal: ${JSON.stringify(solution.journal)}` : "No solver solution is currently available.";
      const messages = [{ role: "system", content: CHAT_SYSTEM }, { role: "system", content: context }, ...next.map((m) => ({ role: m.role, content: m.text }))];
      const raw = await complete(messages, 0.2, MAX_CHAT_TOKENS);
      setChat((x) => [...x, { role: "assistant", text: raw }].slice(-MAX_CHAT_MESSAGES));
    } catch (e: any) { setError(e?.message || "Chat failed."); }
    finally { setBusy(false); setBusyStage(""); }
  }

  const loadingModel = status === "checking" || status === "loading";

  return (
    <main className="ai-shell">
      <header className="ai-topbar glass-nav">
        <div><a href="/" className="back">← Auto Finance Studio</a><h1>AI Accounting Workbench</h1><p>Analyze transactions, validate double-entry logic, and test the local reasoning engine.</p></div>
        <div className={`model-pill ${status}`}><span className="dot" />{status === "ready" ? "LLM Ready" : loadingModel ? "Preparing LLM" : status === "error" ? "Needs attention" : "LLM Offline"}</div>
      </header>

      <section className="ai-grid">
        <aside className="ai-card model-card glass-card">
          <div className="eyebrow">LOCAL RUNTIME</div><h2>Qwen 0.5B</h2><p className="muted">Inference runs in a dedicated worker. The browser UI stays responsive while the model uses the device GPU.</p>
          <div className="progress"><span style={{ width: `${progress}%` }} /></div><small>{statusText}</small>
          <button className="primary interactive" onClick={() => initialize(false)} disabled={loadingModel || status === "ready"}>{status === "ready" ? "Model ready" : loadingModel ? "Preparing…" : "Initialize / resume local LLM"}</button>
          <div className="runtime-check"><span>GPU</span><b>{gpuInfo}</b></div><div className="runtime-check"><span>Storage</span><b>{storageInfo}</b></div>
          {error && <div className="error">{error}</div>}
          <div className="model-note"><b>Model ID</b><code>{MODEL}</code></div>
        </aside>

        <section className="ai-card solver-card glass-card">
          <div className="section-head"><div><div className="eyebrow">AUTO SOLVER</div><h2>Accounting problem → validated journal</h2></div><span className="badge">LLM + validation</span></div>
          <textarea value={problem} onChange={(e) => setProblem(e.target.value)} placeholder="Example: On March 1, ABC Trading paid ₱24,000 cash for six months of rent. Prepare the journal entry and explain the accounts." />
          <div className="actions"><button className="primary interactive" onClick={solve} disabled={!engine || busy}>{busy ? "Analyzing…" : "Analyze & Solve"}</button><button className="ghost interactive" onClick={() => { setProblem(""); setSolution(null); setError(""); setTrace(TRACE); }}>Clear</button></div>

          {(busy || trace.some((x) => x.state === "done")) && <div className="reasoning-panel">
            <div className="reasoning-head"><div><div className="eyebrow">AI ANALYSIS</div><strong>{busy ? busyStage : "Analysis complete"}</strong></div><span className="badge">Visible reasoning trace</span></div>
            <div className="trace-list">{trace.map((item, i) => <div className={`trace-item ${item.state}`} key={item.label}><span className="trace-icon">{item.state === "done" ? "✓" : item.state === "active" ? "•" : i + 1}</span><div><b>{item.label}</b><small>{item.detail}</small></div></div>)}</div>
            <div className="reasoning-disclaimer">Shows the model's user-facing analysis stages and accounting rationale, not private chain-of-thought.</div>
          </div>}

          {busy && <div className="ai-activity"><div className="activity-orb"/><div><strong>{busyStage || "Working…"}</strong><span>Inference is running in a background worker to reduce UI-thread blocking.</span></div><div className="typing"><i/><i/><i/></div></div>}
          {busy && <div className="solution-skeleton"><div className="skeleton sk-title"/><div className="skeleton sk-line"/><div className="skeleton sk-line short"/><div className="skeleton-table"><div/><div/><div/><div/></div></div>}

          {solution && !busy && <div className="solution"><div className="solution-head"><div><span className="badge success">Balanced</span><h3>{solution.businessName ? `${solution.businessName} — Model analysis` : "Model analysis"}</h3></div><div className="totals">Dr {money(total.debit)} · Cr {money(total.credit)}</div></div><p>{solution.analysis}</p>{solution.businessName && <div className="subblock business-detected"><b>Business detected</b><span>{solution.businessName}</span><small>Detected from the problem statement. Confirm or edit this name before using it on reports.</small></div>}{solution.assumptions?.length > 0 && <div className="subblock"><b>Assumptions</b><ul>{solution.assumptions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}<div className="journal-table"><div className="tr th"><span>Account</span><span>Debit</span><span>Credit</span><span>Why</span></div>{solution.journal.map((x, i) => <div className="tr" key={i}><span>{x.account}</span><span>{x.debit ? money(Number(x.debit)) : "—"}</span><span>{x.credit ? money(Number(x.credit)) : "—"}</span><span>{x.explanation}</span></div>)}</div>{solution.checks?.length > 0 && <div className="subblock"><b>Checks</b><ul>{solution.checks.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}</div>}
        </section>

        <section className="ai-card chat-card glass-card">
          <div className="section-head"><div><div className="eyebrow">AI ASSISTANT</div><h2>Talk to the model</h2></div><button className="ghost interactive" onClick={() => setChat([])}>Clear</button></div>
          <div className="chat-log">{chat.length === 0 && <div className="empty"><div className="orb"/><strong>Test the reasoning engine</strong><span>Ask “Why is prepaid rent an asset?” or ask about the current solution.</span></div>}{chat.map((m, i) => <div key={i} className={`bubble ${m.role}`}><span className="role">{m.role === "user" ? "You" : "Local LLM"}</span><div>{m.text}</div></div>)}{busy && chat.length > 0 && <div className="bubble assistant"><span className="role">Local LLM</span><div className="typing"><i/><i/><i/></div></div>}</div>
          <div className="chat-compose"><input value={chatInput} onChange={(e) => setChatInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void sendChat(); }} placeholder={engine ? "Ask the accounting model…" : "Initialize the model first"} disabled={!engine || busy} /><button className="primary interactive" onClick={() => void sendChat()} disabled={!engine || busy || !chatInput.trim()}>Send</button></div>
        </section>
      </section>
    </main>
  );
}
