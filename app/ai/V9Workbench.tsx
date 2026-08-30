"use client";

import { useEffect, useRef, useState } from "react";
import { CreateWebWorkerMLCEngine } from "@mlc-ai/web-llm";
import { buildFastPlan } from "../../lib/ai/orchestrator";
import { normalizeSolverResult, SOLVER_MAX_INPUT_CHARS, SOLVER_MAX_OUTPUT_TOKENS, SOLVER_MODEL, SOLVER_SYSTEM, type SolverResult } from "../../lib/ai/v9-contracts";
import { loadWebLLMState, requestPersistentBrowserStorage, saveWebLLMState } from "../../lib/webllm-persistence";

const money = (n:number) => new Intl.NumberFormat("en-PH",{style:"currency",currency:"PHP"}).format(n || 0);

type Status="idle"|"checking"|"loading"|"ready"|"error";

export default function V9Workbench(){
 const [status,setStatus]=useState<Status>("idle"); const [progress,setProgress]=useState(0); const [statusText,setStatusText]=useState("Local model not initialized");
 const [problem,setProblem]=useState(""); const [solution,setSolution]=useState<SolverResult|null>(null); const [error,setError]=useState(""); const [busy,setBusy]=useState(false); const [stage,setStage]=useState(""); const [fastCount,setFastCount]=useState(0); const [coverage,setCoverage]=useState(0);
 const engineRef=useRef<any>(null); const workerRef=useRef<Worker|null>(null); const initializing=useRef(false);
 async function initialize(){
  if(initializing.current||engineRef.current)return; initializing.current=true; setStatus("checking");setError("");
  try{ const gpu=(navigator as any).gpu;if(!gpu)throw new Error("WebGPU is unavailable on this device/browser.");const adapter=await gpu.requestAdapter({powerPreference:"low-power"});if(!adapter)throw new Error("No compatible GPU adapter was found.");await requestPersistentBrowserStorage();setStatus("loading");
   const previous=loadWebLLMState(SOLVER_MODEL);if(previous)setProgress(previous.progress);if(!workerRef.current)workerRef.current=new Worker(new URL("./webllm.worker.ts",import.meta.url),{type:"module"});
   const engine=await CreateWebWorkerMLCEngine(workerRef.current,SOLVER_MODEL,{initProgressCallback:(p:any)=>{const v=Math.max(0,Math.min(100,Math.round((p?.progress||0)*100)));setProgress(v);setStatusText(p?.text||`Preparing model… ${v}%`);saveWebLLMState({modelId:SOLVER_MODEL,status:v>=100?"ready":"downloading",progress:v,text:p?.text||"Preparing model",updatedAt:Date.now()});}});
   engineRef.current=engine;setStatus("ready");setProgress(100);setStatusText("Local model ready");saveWebLLMState({modelId:SOLVER_MODEL,status:"ready",progress:100,text:"Local model ready",updatedAt:Date.now()});
  }catch(e:any){setStatus("error");setError(e?.message||"WebLLM initialization failed.");setStatusText("Local model unavailable");}finally{initializing.current=false;}
 }
 useEffect(()=>{void initialize();return()=>{workerRef.current?.terminate();workerRef.current=null;engineRef.current=null}},[]);
 async function solve(){
  const input=problem.trim();if(!input)return setError("Enter an accounting problem first.");if(input.length>SOLVER_MAX_INPUT_CHARS)return setError(`Problem is too long. Keep it under ${SOLVER_MAX_INPUT_CHARS.toLocaleString()} characters.`);
  setBusy(true);setError("");setSolution(null);setStage("Fast pass: extracting obvious transactions…");
  try{const plan=buildFastPlan(input);setFastCount(plan.fast.length);setCoverage(plan.coverage);let model:unknown={entries:[],adjustments:[],requestedOutputs:[],assumptions:[],warnings:[]};
   if(plan.needsLLM){ if(!engineRef.current)throw new Error("Local model is still preparing. Wait until it is ready.");setStage("LLM pass: resolving ambiguous transactions…");const prompt=`Accounting problem:\n${input}\n\nHigh-confidence deterministic candidates:\n${JSON.stringify(plan.fast)}`;const result=await engineRef.current.chat.completions.create({messages:[{role:"system",content:SOLVER_SYSTEM},{role:"user",content:prompt}],temperature:0.05,max_tokens:SOLVER_MAX_OUTPUT_TOKENS});model=JSON.parse(result?.choices?.[0]?.message?.content?.match(/\{[\s\S]*\}/)?.[0]||"{}");}
   setStage("Validating structured result…");const normalized=normalizeSolverResult(model);const merged=plan.fast.length?{...normalized,entries:[...normalized.entries,...plan.fast.map((x,i)=>({description:x.description,lines:[{account:x.debit,debit:x.amount,credit:0,memo:x.rationale},{account:x.credit,debit:0,credit:x.amount}],date:undefined}))]}:normalized;
   setSolution(merged);setStage("Complete");
  }catch(e:any){setError(e?.message||"Solver failed.");}finally{setBusy(false);}
 }
 const total=solution?.entries.reduce((s,e)=>s+e.lines.reduce((x,l)=>x+Number(l.debit||0),0),0)||0;
 const credit=solution?.entries.reduce((s,e)=>s+e.lines.reduce((x,l)=>x+Number(l.credit||0),0),0)||0;
 return <main className="v9-shell">
  <header className="v9-top"><div><div className="v9-label">YOHO V9 · MAX</div><h1 className="v9-title">AI Accounting Engine</h1><p className="v9-sub">Fast deterministic extraction first. Local WebLLM only handles ambiguity. The accounting result is normalized before it reaches the UI.</p></div><div className="v9-status"><span className="v9-dot"/>{status==="ready"?"LLM Ready":status==="loading"||status==="checking"?"Preparing":status==="error"?"Needs attention":"Offline"}</div></header>
  <div className="v9-grid"><aside className="v9-card"><div className="v9-label">LOCAL RUNTIME</div><h2>Qwen 0.5B</h2><p className="v9-muted">Worker inference · cached model · compact JSON · no artificial stage delays.</p><div className="v9-progress" style={{"--p":`${progress}%`} as React.CSSProperties}><i/></div><div className="v9-muted">{statusText}</div><div className="v9-actions"><button className="v9-btn v9-primary" onClick={()=>void initialize()} disabled={status==="ready"||status==="loading"}>{status==="ready"?"Ready":"Initialize / resume"}</button></div><div className="v9-kv"><span>Model</span><b>{SOLVER_MODEL.split("-")[0]}</b></div><div className="v9-kv"><span>Max output</span><b>{SOLVER_MAX_OUTPUT_TOKENS} tokens</b></div><div className="v9-kv"><span>Input cap</span><b>{SOLVER_MAX_INPUT_CHARS.toLocaleString()} chars</b></div></aside>
  <section className="v9-card"><div className="v9-label">AUTO SOLVER</div><h2>Messy problem → structured accounting</h2><p className="v9-muted">Paste an unstructured accounting problem. Yoho extracts high-confidence events locally before asking the model to resolve only what remains ambiguous.</p><textarea className="v9-textarea" value={problem} onChange={e=>setProblem(e.target.value)} placeholder="Paste a messy accounting problem here…"/><div className="v9-actions"><button className="v9-btn v9-primary" onClick={()=>void solve()} disabled={busy||!problem.trim()}>{busy?stage||"Working…":"Analyze & Solve"}</button><button className="v9-btn v9-secondary" onClick={()=>{setProblem("");setSolution(null);setError("")}}>Clear</button></div>
   {busy&&<div className="v9-result"><span className="v9-badge">{stage}</span></div>}{error&&<div className="v9-error">{error}</div>}
   {solution&&<div className="v9-result"><div className="v9-actions"><span className="v9-badge">Validated structure</span><span className="v9-muted">Fast pass: {fastCount} · coverage: {Math.round(coverage*100)}%</span></div><div className="v9-kv"><span>Debit total</span><b>{money(total)}</b></div><div className="v9-kv"><span>Credit total</span><b>{money(credit)}</b></div><h3 style={{marginTop:20}}>Journal candidates</h3><table className="v9-table"><thead><tr><th>Entry</th><th>Accounts</th><th>Amount</th></tr></thead><tbody>{solution.entries.map((e,i)=><tr key={`${e.description}-${i}`}><td>{e.description}</td><td>{e.lines.map(l=>`${l.debit>0?"Dr":"Cr"} ${l.account}`).join(" · ")}</td><td>{money(e.lines.reduce((s,l)=>s+Math.max(l.debit,l.credit),0))}</td></tr>)}</tbody></table>{solution.warnings.length>0&&<div className="v9-warning">{solution.warnings.join(" · ")}</div>}</div>}
  </section></div>
 </main>
}
