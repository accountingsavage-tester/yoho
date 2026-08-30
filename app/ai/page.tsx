"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CreateMLCEngine } from "@mlc-ai/web-llm";
import { loadWebLLMState, requestPersistentBrowserStorage, saveWebLLMState } from "../../lib/webllm-persistence";

const MODEL = "Qwen2-0.5B-Instruct-q4f16_1-MLC";

type Status = "idle" | "checking" | "loading" | "ready" | "error";
type JournalLine = { account: string; debit: number; credit: number; explanation: string };
type Solution = { analysis: string; assumptions: string[]; journal: JournalLine[]; checks: string[]; outputs: string[] };

const money = (n: number) => new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(n || 0);

function extractJson(text: string) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  const candidate = fenced?.[1] || text.match(/\{[\s\S]*\}/)?.[0];
  if (!candidate) throw new Error("The model did not return structured accounting data.");
  return JSON.parse(candidate);
}

const SYSTEM = `You are an accounting reasoning assistant for a double-entry bookkeeping application.
Analyze the user's accounting problem carefully before proposing entries.
Use standard accrual accounting and normal debit/credit rules.
Never invent missing facts. State assumptions explicitly.
Return ONLY valid JSON with this exact shape:
{"analysis":"string","assumptions":["string"],"journal":[{"account":"string","debit":0,"credit":0,"explanation":"string"}],"checks":["string"],"outputs":["string"]}
Numbers must be plain numbers. Every journal line must have either debit or credit, not both.
The journal must balance. If the problem is ambiguous or impossible to solve, explain why in analysis and assumptions rather than fabricating an answer.`;

export default function AIWorkbench() {
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("Local model not initialized");
  const [engine, setEngine] = useState<any>(null);
  const [gpuInfo, setGpuInfo] = useState("Not checked");
  const [storageInfo, setStorageInfo] = useState("Browser storage not checked");
  const [problem, setProblem] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [chat, setChat] = useState<{ role: "user" | "assistant"; text: string }[]>([]);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const initializing = useRef(false);

  const total = useMemo(() => solution?.journal.reduce((a, x) => ({ debit: a.debit + Number(x.debit || 0), credit: a.credit + Number(x.credit || 0) }), { debit: 0, credit: 0 }) || { debit: 0, credit: 0 }, [solution]);

  async function initialize(auto = false) {
    if (initializing.current || engine || status === "ready") return;
    initializing.current = true;
    setStatus("checking"); setError(""); setStatusText(auto ? "Restoring local model…" : "Checking browser GPU support…");
    try {
      const previous = loadWebLLMState(MODEL);
      if (previous && previous.status === "downloading") {
        setProgress(previous.progress);
        setStatusText(`Resuming model download from ${previous.progress}%…`);
      } else if (previous?.status === "ready") {
        setProgress(100);
        setStatusText("Restoring cached model…");
      }

      const gpu = (navigator as any).gpu;
      if (!gpu) {
        setGpuInfo("WebGPU unavailable");
        setStatus("error");
        setStatusText("Local AI unavailable on this device");
        setError("This browser does not expose WebGPU. The model cache can remain on the device, but local inference requires a WebGPU-capable GPU.");
        return;
      }
      const adapter = await gpu.requestAdapter();
      if (!adapter) {
        setGpuInfo("No compatible GPU adapter");
        setStatus("error");
        setStatusText("Local AI unavailable on this device");
        setError("No compatible GPU adapter was found. If the model was previously downloaded, it remains cached; this device simply cannot execute WebLLM locally.");
        return;
      }
      setGpuInfo("WebGPU adapter detected");
      const persistent = await requestPersistentBrowserStorage();
      setStorageInfo(persistent ? "Persistent storage enabled" : "Browser storage available");
      setStatus("loading");
      saveWebLLMState({ modelId: MODEL, status: "downloading", progress: previous?.progress || 0, text: "Initializing WebLLM", updatedAt: Date.now() });

      const next = await CreateMLCEngine(MODEL, {
        initProgressCallback: (p: any) => {
          const value = Math.max(0, Math.min(100, Math.round((p?.progress || 0) * 100)));
          setProgress(value);
          setStatusText(p?.text || `Downloading model assets… ${value}%`);
          saveWebLLMState({ modelId: MODEL, status: value >= 100 ? "ready" : "downloading", progress: value, text: p?.text || "Downloading model assets", updatedAt: Date.now() });
        },
      });
      setEngine(next);
      setStatus("ready");
      setProgress(100);
      setStatusText("Local LLM ready — cached on this device");
      saveWebLLMState({ modelId: MODEL, status: "ready", progress: 100, text: "Local LLM ready", updatedAt: Date.now() });
    } catch (e: any) {
      setStatus("error");
      setStatusText("Local LLM could not start");
      setError(e?.message || "WebLLM initialization failed.");
      saveWebLLMState({ modelId: MODEL, status: "error", progress, text: e?.message || "Initialization failed", updatedAt: Date.now() });
    } finally {
      initializing.current = false;
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const saved = loadWebLLMState(MODEL);
      if (saved) {
        if (cancelled) return;
        setProgress(saved.progress);
        if (saved.status === "ready") setStatusText("Cached model found — restoring…");
        if (saved.status === "downloading") setStatusText(`Previous download found — resuming from ${saved.progress}%…`);
      }
      if (!cancelled) await initialize(true);
    })();
    return () => { cancelled = true; };
    // initialize is intentionally stable through the ref guard; auto-restore should run once per page mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function complete(messages: any[], temperature = 0.1) {
    if (!engine) throw new Error("Initialize the local model first.");
    const result = await engine.chat.completions.create({ messages, temperature, max_tokens: 1400 });
    return result?.choices?.[0]?.message?.content || "";
  }

  async function solve() {
    if (!problem.trim()) return setError("Enter an accounting problem first.");
    setBusy(true); setError("");
    try {
      const raw = await complete([{ role: "system", content: SYSTEM }, { role: "user", content: `Solve this accounting problem:\n\n${problem.trim()}` }]);
      const parsed = extractJson(raw) as Solution;
      if (!Array.isArray(parsed.journal)) throw new Error("Invalid journal returned by model.");
      const debit = parsed.journal.reduce((s, x) => s + Number(x.debit || 0), 0);
      const credit = parsed.journal.reduce((s, x) => s + Number(x.credit || 0), 0);
      if (Math.abs(debit - credit) > 0.005) throw new Error(`Model returned an unbalanced entry (${money(debit)} Dr vs ${money(credit)} Cr).`);
      setSolution(parsed);
    } catch (e: any) { setError(e?.message || "The accounting problem could not be solved."); }
    finally { setBusy(false); }
  }

  async function sendChat() {
    if (!chatInput.trim()) return;
    const text = chatInput.trim(); setChatInput(""); setError("");
    const next = [...chat, { role: "user" as const, text }]; setChat(next); setBusy(true);
    try {
      const raw = await complete([{ role: "system", content: "You are a concise accounting tutor. Explain journal entries, debit/credit logic, adjusting entries, and financial statements accurately. Do not fabricate facts." }, ...next.map((m) => ({ role: m.role, content: m.text }))], 0.2);
      setChat((x) => [...x, { role: "assistant", text: raw }]);
    } catch (e: any) { setError(e?.message || "Chat failed."); }
    finally { setBusy(false); }
  }

  const loadingModel = status === "checking" || status === "loading";

  return (
    <main className="ai-shell">
      <header className="ai-topbar glass-nav">
        <div><a href="/" className="back">← Auto Finance Studio</a><h1>AI Accounting Workbench</h1><p>Analyze transactions, validate double-entry logic, and test the local reasoning engine before posting anything.</p></div>
        <div className={`model-pill ${status}`}><span className="dot" />{status === "ready" ? "LLM Ready" : loadingModel ? "Preparing LLM" : status === "error" ? "Needs attention" : "LLM Offline"}</div>
      </header>

      <section className="ai-grid">
        <aside className="ai-card model-card glass-card">
          <div className="eyebrow">LOCAL RUNTIME</div><h2>Qwen 0.5B</h2><p className="muted">The model is cached by WebLLM and restored automatically when you return. A compatible WebGPU adapter is still required for local inference.</p>
          <div className="progress"><span style={{ width: `${progress}%` }} /></div>
          <small>{statusText}</small>
          <button className="primary interactive" onClick={() => initialize(false)} disabled={loadingModel || status === "ready"}>{status === "ready" ? "Model ready" : loadingModel ? "Preparing…" : "Initialize / resume local LLM"}</button>
          <div className="runtime-check"><span>GPU</span><b>{gpuInfo}</b></div>
          <div className="runtime-check"><span>Storage</span><b>{storageInfo}</b></div>
          {error && <div className="error">{error}</div>}
          <div className="model-note"><b>Model ID</b><code>{MODEL}</code></div>
        </aside>

        <section className="ai-card solver-card glass-card">
          <div className="section-head"><div><div className="eyebrow">AUTO SOLVER</div><h2>Accounting problem → validated journal</h2></div><span className="badge">LLM + validation</span></div>
          <textarea value={problem} onChange={(e) => setProblem(e.target.value)} placeholder="Example: On March 1, the business paid ₱24,000 cash for six months of rent. Prepare the journal entry and explain the accounts." />
          <div className="actions"><button className="primary interactive" onClick={solve} disabled={!engine || busy}>{busy ? "Analyzing…" : "Analyze & Solve"}</button><button className="ghost interactive" onClick={() => { setProblem(""); setSolution(null); setError(""); }}>Clear</button></div>
          {busy && <div className="solution-skeleton"><div className="skeleton sk-title"/><div className="skeleton sk-line"/><div className="skeleton sk-line short"/><div className="skeleton-table"><div/><div/><div/><div/></div></div>}
          {solution && !busy && <div className="solution"><div className="solution-head"><div><span className="badge success">Balanced</span><h3>Model analysis</h3></div><div className="totals">Dr {money(total.debit)} · Cr {money(total.credit)}</div></div><p>{solution.analysis}</p>{solution.assumptions?.length > 0 && <div className="subblock"><b>Assumptions</b><ul>{solution.assumptions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}<div className="journal-table"><div className="tr th"><span>Account</span><span>Debit</span><span>Credit</span><span>Why</span></div>{solution.journal.map((x, i) => <div className="tr" key={i}><span>{x.account}</span><span>{x.debit ? money(Number(x.debit)) : "—"}</span><span>{x.credit ? money(Number(x.credit)) : "—"}</span><span>{x.explanation}</span></div>)}</div>{solution.checks?.length > 0 && <div className="subblock"><b>Checks</b><ul>{solution.checks.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}</div>}
        </section>

        <section className="ai-card chat-card glass-card">
          <div className="section-head"><div><div className="eyebrow">LLM TEST CHAT</div><h2>Talk to the model</h2></div><button className="ghost interactive" onClick={() => setChat([])}>Clear</button></div>
          <div className="chat-log">{chat.length === 0 && <div className="empty"><div className="orb"/><strong>Test the reasoning engine</strong><span>Ask “Why is prepaid rent an asset?” or “Explain adjusting entries.”</span></div>}{chat.map((m, i) => <div key={i} className={`bubble ${m.role}`}><span className="role">{m.role === "user" ? "You" : "Local LLM"}</span><div>{m.text}</div></div>)}{busy && chat.length > 0 && <div className="bubble assistant"><span className="role">Local LLM</span><div className="typing"><i/><i/><i/></div></div>}</div>
          <div className="chat-compose"><input value={chatInput} onChange={(e) => setChatInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") sendChat(); }} placeholder={engine ? "Ask the accounting model…" : "Initialize the model first"} disabled={!engine || busy} /><button className="primary interactive" onClick={sendChat} disabled={!engine || busy || !chatInput.trim()}>Send</button></div>
        </section>
      </section>
    </main>
  );
}
