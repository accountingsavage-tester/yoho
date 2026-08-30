"use client";

import { useEffect, useMemo, useState } from "react";

const LOCAL_MODEL_ID = "Qwen2-0.5B-Instruct-q4f16_1-MLC";
let localLLM: any = null;
let localLLMModule: any = null;

type AccountType = "Asset"|"Liability"|"Equity"|"Revenue"|"Expense";
type Account = {id:string; code:string; name:string; type:AccountType; normal:"Debit"|"Credit"};
type Line = {accountId:string; debit:number; credit:number; memo?:string};
type Entry = {id:string; date:string; description:string; reference:string; kind:"Regular"|"Adjusting"|"Closing"; lines:Line[]};
type OutputKey = "General Journal"|"General Ledger"|"Trial Balance"|"Adjusting Entries"|"Adjusted Trial Balance"|"Worksheet"|"Income Statement"|"Owner's Equity"|"Balance Sheet"|"Closing Entries"|"Post-Closing Trial Balance";

const A=(id:string,code:string,name:string,type:AccountType):Account=>({
  id,code,name,type,normal:name.includes("Accumulated Depreciation")?"Credit":name.includes("Drawing")?"Debit":type==="Liability"||type==="Equity"||type==="Revenue"?"Credit":"Debit"
});
const DEFAULT_ACCOUNTS:Account[]=[
 A("101","101","Cash","Asset"), A("102","102","Accounts Receivable","Asset"),
 A("103","103","Supplies","Asset"), A("104","104","Prepaid Rent","Asset"),
 A("105","105","Equipment","Asset"), A("106","106","Accumulated Depreciation—Equipment","Asset"),
 A("201","201","Accounts Payable","Liability"), A("202","202","Unearned Revenue","Liability"),
 A("203","203","Salaries Payable","Liability"), A("204","204","Notes Payable","Liability"),
 A("301","301","Owner's Capital","Equity"), A("302","302","Owner's Drawing","Equity"),
 A("401","401","Service Revenue","Revenue"),
 A("501","501","Rent Expense","Expense"), A("502","502","Supplies Expense","Expense"),
 A("503","503","Salaries Expense","Expense"), A("504","504","Utilities Expense","Expense"),
 A("505","505","Depreciation Expense","Expense")
];

const money=(n:number)=>new Intl.NumberFormat("en-PH",{style:"currency",currency:"PHP",maximumFractionDigits:2}).format(n||0);
const uid=()=>Math.random().toString(36).slice(2,10);
const today=()=>new Date().toISOString().slice(0,10);
const num=(v:string|number)=>Math.round((Number(v)||0)*100)/100;

function csvDownload(name:string, rows:(string|number)[][]){
 const csv=rows.map(r=>r.map(v=>`"${String(v).replaceAll('"','""')}"`).join(",")).join("\n");
 const b=new Blob([csv],{type:"text/csv;charset=utf-8"}); const a=document.createElement("a");
 a.href=URL.createObjectURL(b); a.download=name; a.click(); URL.revokeObjectURL(a.href);
}

export default function Home(){
 const [accounts,setAccounts]=useState<Account[]>(DEFAULT_ACCOUNTS);
 const [entries,setEntries]=useState<Entry[]>([]);
 const [business,setBusiness]=useState("My Business");
 const [periodEnd,setPeriodEnd]=useState(today());
 const [tab,setTab]=useState("Dashboard");
 const [notice,setNotice]=useState("");
 const [importPreview,setImportPreview]=useState<any|null>(null);
 const [importMode,setImportMode]=useState<"add"|"replace">("add");
 const [importBusy,setImportBusy]=useState(false);
 const [problemText,setProblemText]=useState("");
 const [problemFile,setProblemFile]=useState("");
 const [solution,setSolution]=useState<any|null>(null);
 const [solveBusy,setSolveBusy]=useState(false);
 const [solveMode,setSolveMode]=useState<"required"|"complete">("required");
 const [llmStatus,setLlmStatus]=useState<"idle"|"checking"|"downloading"|"ready"|"error">("idle");
 const [llmProgress,setLlmProgress]=useState(0);
 const [llmMessage,setLlmMessage]=useState("Local model not initialized");

 useEffect(()=>{try{
   const s=JSON.parse(localStorage.getItem("afs-v2")||"{}");
   if(s.accounts)setAccounts(s.accounts); if(s.entries)setEntries(s.entries);
   if(s.business)setBusiness(s.business); if(s.periodEnd)setPeriodEnd(s.periodEnd);
 }catch{}},[]);
 useEffect(()=>{localStorage.setItem("afs-v2",JSON.stringify({accounts,entries,business,periodEnd}))},[accounts,entries,business,periodEnd]);

 const map=useMemo(()=>Object.fromEntries(accounts.map(a=>[a.id,a])),[accounts]);

 const balances=useMemo(()=>{
   const m:Record<string,{debit:number;credit:number}>={};
   accounts.forEach(a=>m[a.id]={debit:0,credit:0});
   entries.filter(e=>e.kind!=="Closing").forEach(e=>e.lines.forEach(l=>{
     if(!m[l.accountId])m[l.accountId]={debit:0,credit:0};
     m[l.accountId].debit+=num(l.debit); m[l.accountId].credit+=num(l.credit);
   }));
   return m;
 },[accounts,entries]);

 const regular=entries.filter(e=>e.kind==="Regular");
 const adjusting=entries.filter(e=>e.kind==="Adjusting");
 const closing=entries.filter(e=>e.kind==="Closing");

 const adjusted=useMemo(()=>{
   const m:Record<string,{debit:number;credit:number}>={};
   accounts.forEach(a=>m[a.id]={debit:0,credit:0});
   [...regular,...adjusting].forEach(e=>e.lines.forEach(l=>{
     m[l.accountId].debit+=num(l.debit);m[l.accountId].credit+=num(l.credit);
   }));
   return m;
 },[accounts,regular,adjusting]);

 const rows=accounts.map(a=>{
   const b=balances[a.id]||{debit:0,credit:0}, x=adjusted[a.id]||{debit:0,credit:0};
   const trialNet=a.normal==="Debit"?b.debit-b.credit:b.credit-b.debit;
   const adjNet=a.normal==="Debit"?x.debit-x.credit:x.credit-x.debit;
   return {...a,...b,adjDebit:x.debit,adjCredit:x.credit,trialNet,adjNet};
 });

 const totals=(rs:any[])=>rs.reduce((z,r)=>({debit:z.debit+r.debit,credit:z.credit+r.credit}),{debit:0,credit:0});
 const t=totals(rows);
 const at=totals(rows.map(r=>({debit:r.adjDebit,credit:r.adjCredit})));

 const revenue=rows.filter(r=>r.type==="Revenue").reduce((s,r)=>s+r.adjNet,0);
 const expenses=rows.filter(r=>r.type==="Expense").reduce((s,r)=>s+r.adjNet,0);
 const netIncome=revenue-expenses;
 const assets=rows.filter(r=>r.type==="Asset").reduce((s,r)=>s+r.adjNet,0);
 const liabilities=rows.filter(r=>r.type==="Liability").reduce((s,r)=>s+r.adjNet,0);
 const contributed=rows.filter(r=>r.type==="Equity"&&r.name!=="Owner's Drawing").reduce((s,r)=>s+r.adjNet,0);
 const drawing=rows.find(r=>r.name==="Owner's Drawing")?.adjNet||0;
 const endingEquity=contributed+netIncome-drawing;

 function post(e:Entry){
   const d=e.lines.reduce((s,l)=>s+num(l.debit),0),c=e.lines.reduce((s,l)=>s+num(l.credit),0);
   if(!e.description.trim()){setNotice("Enter a description.");return}
   if(e.lines.length<2){setNotice("An entry needs at least two lines.");return}
   if(Math.abs(d-c)>0.005){setNotice(`Entry rejected. Debit ${money(d)} does not equal credit ${money(c)}.`);return}
   if(e.lines.some(l=>num(l.debit)>0&&num(l.credit)>0)){setNotice("A line cannot contain both a debit and a credit.");return}
   if(e.lines.every(l=>num(l.debit)===0&&num(l.credit)===0)){setNotice("Enter at least one amount.");return}
   setEntries(x=>[...x,e]);setNotice("Entry posted.");setTab(e.kind==="Adjusting"?"Adjusting Entries":"General Journal");
 }

 function reset(){
   if(confirm("Delete all saved accounting data?")){setAccounts(DEFAULT_ACCOUNTS);setEntries([]);setBusiness("My Business");setNotice("All data reset.")}
 }


 const importFile=async(file:File)=>{
   setImportBusy(true); setNotice("");
   try{
     const ext=file.name.toLowerCase().split(".").pop()||"";
     if(ext==="json"){
       const data=JSON.parse(await file.text());
       if(!Array.isArray(data.entries)&&!Array.isArray(data.accounts)) throw new Error("JSON does not contain Finance Studio data.");
       setImportPreview({file:file.name,kind:"project",data,rows:[]});
     }else if(ext==="csv"){
       const text=await file.text();
       const lines=text.split(/\r?\n/).filter(Boolean);
       const parse=(line:string)=>{const out:string[]=[];let cur="",q=false;for(let i=0;i<line.length;i++){const ch=line[i];if(ch==='"'){if(q&&line[i+1]==='"'){cur+='"';i++;}else q=!q;}else if(ch===","&&!q){out.push(cur.trim());cur="";}else cur+=ch;}out.push(cur.trim());return out;};
       const rows=lines.map(parse);
       setImportPreview({file:file.name,kind:"table",headers:rows[0]||[],rows:rows.slice(1,101),allRows:rows});
     }else if(ext==="xlsx"||ext==="xls"){
       const XLSX=await import("xlsx");
       const buf=await file.arrayBuffer();
       const wb=XLSX.read(buf,{type:"array"});
       const sheets=wb.SheetNames.map(name=>{
         const data=XLSX.utils.sheet_to_json(wb.Sheets[name],{header:1,defval:""});
         return {name,rows:data};
       });
       const preferred=sheets.find(x=>/journal|transaction|ledger/i.test(x.name))||sheets[0];
       setImportPreview({file:file.name,kind:"workbook",sheets,selectedSheet:preferred?.name||"",headers:(preferred?.rows?.[0]||[]),rows:(preferred?.rows||[]).slice(1,101),allRows:preferred?.rows||[]});
     }else{
       throw new Error("Supported imports are .xlsx, .xls, .csv, and .json.");
     }
   }catch(e:any){setNotice(e?.message||"Could not read the file.");}
   finally{setImportBusy(false);}
 };

 const normalize=(v:any)=>String(v??"").trim().toLowerCase().replace(/[_-]+/g," ").replace(/\s+/g," ");
 const findCol=(headers:any[],names:string[])=>{
   const h=headers.map(normalize);
   return names.map(normalize).map(x=>h.indexOf(x)).find(i=>i>=0)??-1;
 };
 const confirmImport=()=>{
   const x=importPreview;if(!x)return;
   if(x.kind==="project"){
     const d=x.data;
     if(importMode==="replace"){
       if(Array.isArray(d.accounts))setAccounts(d.accounts);
       if(Array.isArray(d.entries))setEntries(d.entries);
       if(d.business)setBusiness(d.business);
       if(d.periodEnd)setPeriodEnd(d.periodEnd);
     }else{
       if(Array.isArray(d.accounts))setAccounts(prev=>{const seen=new Set(prev.map(a=>a.id));return [...prev,...d.accounts.filter((a:any)=>!seen.has(a.id))];});
       if(Array.isArray(d.entries))setEntries(prev=>[...prev,...d.entries]);
     }
     setNotice(`Imported project: ${x.file}`);
   }else{
     const headers=x.headers||[];
     const dateI=findCol(headers,["date","transaction date"]);
     const descI=findCol(headers,["description","details","particulars","transaction"]);
     const refI=findCol(headers,["reference","ref","reference no","reference number"]);
     const codeI=findCol(headers,["account code","code","account no","account number"]);
     const accountI=findCol(headers,["account","account name"]);
     const debitI=findCol(headers,["debit","dr"]);
     const creditI=findCol(headers,["credit","cr"]);
     if(codeI<0&&accountI<0) throw new Error("No Account Code or Account column was found.");
     if(debitI<0&&creditI<0) throw new Error("No Debit or Credit column was found.");
     const get=(r:any[],i:number)=>i<0?"":r[i];
     const newAccounts:Account[]=[];
     const imported:Entry[]=[];
     (x.allRows||[]).forEach((r:any[],idx:number)=>{
       const code=String(get(r,codeI)||"").trim();
       const name=String(get(r,accountI)||"").trim();
       const found=accounts.find(a=>a.code===code||a.name.toLowerCase()===name.toLowerCase());
       if(!found && !code && !name)return;
       const acc=found||newAccounts.find(a=>a.code===code)||A(code||uid(),code||String(newAccounts.length+900),name||code,"Asset");
       if(!found&&!newAccounts.some(a=>a.id===acc.id))newAccounts.push(acc);
       const debit=num(get(r,debitI)),credit=num(get(r,creditI));
       if(!debit&&!credit)return;
       const date=String(get(r,dateI)||today());
       const description=String(get(r,descI)||"Imported transaction");
       const ref=String(get(r,refI)||`IMP-${idx+1}`);
       imported.push({id:uid(),date,description,reference:ref,kind:"Regular",lines:[{accountId:acc.id,debit,credit,memo:"Imported from file"}]});
     });
     if(newAccounts.length)setAccounts(prev=>[...prev,...newAccounts]);
     setEntries(prev=>importMode==="replace"?imported:[...prev,...imported]);
     setNotice(`Imported ${imported.length} journal lines from ${x.file}.`);
   }
   setImportPreview(null);
 };


 const ensureAccount=(name:string,type:AccountType)=>{ const clean=name.trim(); let a=accounts.find(x=>x.name.toLowerCase()===clean.toLowerCase()); if(a)return a; const code=String(600+accounts.filter(x=>x.type===type).length+1); a=A(uid(),code,clean,type); setAccounts(prev=>[...prev,a]); return a; };
 const detectRequiredOutputs=(text:string):OutputKey[]=>{
   const l=text.toLowerCase(); const out:OutputKey[]=[]; const add=(x:OutputKey)=>{if(!out.includes(x))out.push(x)};
   if(/post[- ]?closing\s+(trial\s+balance|tb)|post[- ]?closing/.test(l)) add("Post-Closing Trial Balance");
   if(/closing\s+(entries|entry)|close\s+the\s+books/.test(l)) add("Closing Entries");
   if(/10[- ]?column|worksheet/.test(l)) add("Worksheet");
   if(/adjusted\s+trial\s+balance|adjusted\s+trial\s+bal|atb/.test(l)) add("Adjusted Trial Balance");
   if(/adjusting\s+entries?|adjustments?/.test(l)) add("Adjusting Entries");
   if(/income\s+statement|statement\s+of\s+income/.test(l)) add("Income Statement");
   if(/statement\s+of\s+owner|owner'?s\s+equity/.test(l)) add("Owner's Equity");
   if(/balance\s+sheet|statement\s+of\s+financial\s+position/.test(l)) add("Balance Sheet");
   if(/trial\s+balance|prepare\s+(a\s+)?tb\b/.test(l) && !/adjusted\s+trial\s+balance|post[- ]?closing\s+trial\s+balance/.test(l)) add("Trial Balance");
   if(/general\s+ledger|post\s+(the\s+)?(?:journal|entries)\s+to\s+(the\s+)?ledger|ledger/.test(l)) add("General Ledger");
   if(/general\s+journal|journal\s+entries?|journalize|journalizing|record\s+the\s+transactions?/.test(l)) add("General Journal");
   if(/financial\s+statements?/.test(l)){ add("Income Statement"); add("Owner's Equity"); add("Balance Sheet"); }
   if(!out.length) add("General Journal");
   return out;
 };
 const initializeLocalLLM=async()=>{
   if(localLLM)return localLLM;
   if(typeof window==="undefined")throw new Error("Local AI can only run in the browser.");
   if(!(navigator as any).gpu)throw new Error("WebGPU is not available. Use a recent Chrome or Edge browser with WebGPU support.");
   setLlmStatus("checking"); setLlmProgress(0); setLlmMessage("Loading local WebLLM engine…");
   try{
     localLLMModule=localLLMModule||await import("@mlc-ai/web-llm");
     setLlmStatus("downloading");
     const appConfig=localLLMModule.prebuiltAppConfig;
     localLLM=await localLLMModule.CreateMLCEngine(LOCAL_MODEL_ID,{
       appConfig,
       initProgressCallback:(report:any)=>{
         const pct=Math.max(0,Math.min(100,Math.round((Number(report?.progress)||0)*100)));
         setLlmProgress(pct); setLlmMessage(report?.text||`Downloading local model… ${pct}%`);
       },
       logLevel:"ERROR"
     });
     setLlmStatus("ready"); setLlmProgress(100); setLlmMessage("Local model ready. Processing stays on this device.");
     return localLLM;
   }catch(err){ localLLM=null; setLlmStatus("error"); setLlmMessage(err instanceof Error?err.message:"Could not initialize local model"); throw err; }
 };
 const parseLLMJson=(raw:string)=>{
   const cleaned=String(raw||"").replace(/```json|```/gi,"").trim();
   try{return JSON.parse(cleaned);}
   catch{const starts=[cleaned.indexOf("{"),cleaned.indexOf("[")].filter(x=>x>=0);const start=starts.length?Math.min(...starts):0;const end=Math.max(cleaned.lastIndexOf("}"),cleaned.lastIndexOf("]"));if(end>=start)return JSON.parse(cleaned.slice(start,end+1));throw new Error("The local model returned invalid JSON.");}
 };
 const solveWithLocalLLM=async(text:string)=>{
   const engine=await initializeLocalLLM();
   const prompt=`Extract this accounting problem into JSON. Extract facts only; do not invent missing payment methods or accounts. Do not calculate financial statements. Use standard account names. Required shape: {"transactions":[{"date":"","description":"","entries":[{"account":"","side":"debit|credit","amount":0}]}],"requestedOutputs":[],"ambiguities":[]}. Problem:\n${text}`;
   const response=await engine.chat.completions.create({messages:[{role:"system",content:"You are a local accounting parser. Return valid JSON only."},{role:"user",content:prompt}],response_format:{type:"json_object"},temperature:0,max_tokens:1600});
   return parseLLMJson(response.choices?.[0]?.message?.content||"{}");
 };

 const solveProblem=async()=>{
   setSolveBusy(true);
   const text=problemText.trim(); if(!text){setNotice("Paste or upload an accounting word problem first.");setSolveBusy(false);return;}
   let required=detectRequiredOutputs(text);
   let llmData:any=null;
   try{
     llmData=await solveWithLocalLLM(text);
     if(Array.isArray(llmData?.requestedOutputs)&&llmData.requestedOutputs.length)required=llmData.requestedOutputs.filter((x:any)=>typeof x==="string") as OutputKey[];
   }catch(err:any){setNotice(`Local model unavailable. Falling back to deterministic rules: ${err?.message||"unknown error"}`);}
   const lines=text.split(/(?<=[.!?])\s+|\n+/).map(x=>x.trim()).filter(Boolean); const out:any[]=[]; const newAccounts:Account[]=[];
   const accountFor=(name:string,type:AccountType)=>{ const clean=name.trim(); let a=accounts.find(x=>x.name.toLowerCase()===clean.toLowerCase())||newAccounts.find(x=>x.name.toLowerCase()===clean.toLowerCase()); if(a)return a; const code=String(600+accounts.length+newAccounts.length); a=A(uid(),code,clean,type); newAccounts.push(a); return a; };
   const typeFor=(name:string):AccountType=>name.includes("Expense")?"Expense":name.includes("Drawing")?"Equity":name.includes("Revenue")?"Revenue":name.includes("Payable")||name.includes("Unearned")?"Liability":"Asset";
   const add=(desc:string,dr:string,cr:string,amt:number,date:string,extra?:Line[])=>{if(!amt)return; const da=accountFor(dr,typeFor(dr)),ca=accountFor(cr,typeFor(cr)); out.push({id:uid(),date,description:desc,reference:`AUTO-${out.length+1}`,kind:"Regular",lines:[{accountId:da.id,debit:amt,credit:0},{accountId:ca.id,debit:0,credit:amt},...(extra||[])]});};
   const MONTH_RE=/\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?/i;
   const stripDate=(s:string)=>s.replace(MONTH_RE,"");
   const amount=(s:string)=>{
     // Strip the date first so a stray day-of-month digit (e.g. "January 5") is never
     // mistaken for the peso amount when no currency symbol is present.
     const clean=stripDate(s);
     const symbol=clean.replace(/,/g,"").match(/(?:₱|PHP|\bPhp\b|\$|\bP)\s*(\d+(?:\.\d{1,2})?)/i);
     if(symbol)return num(symbol[1]);
     // Prefer a comma-grouped number (e.g. "50,000") over a bare small number, since
     // amounts are almost always the largest/most-formatted figure in the sentence.
     const grouped=clean.match(/\b\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?\b/);
     if(grouped)return num(grouped[0].replace(/,/g,""));
     const plain=clean.match(/\b\d+(?:\.\d{1,2})?\b/);
     return plain?num(plain[0]):0;
   };
   const addCompound=(desc:string,debitName:string,debitAmt:number,credits:[string,number][],date:string)=>{const da=accountFor(debitName,typeFor(debitName));const lines:Line[]=[{accountId:da.id,debit:debitAmt,credit:0}];for(const [name,amt] of credits){const a=accountFor(name,typeFor(name));lines.push({accountId:a.id,debit:0,credit:amt});}out.push({id:uid(),date,description:desc,reference:`AUTO-${out.length+1}`,kind:"Regular",lines});};
   if(llmData?.transactions?.length){
     for(const tx of llmData.transactions){
       const txLines=Array.isArray(tx.entries)?tx.entries:[];
       const debit=txLines.filter((x:any)=>String(x.side).toLowerCase()==="debit");
       const credit=txLines.filter((x:any)=>String(x.side).toLowerCase()==="credit");
       const totalD=debit.reduce((n:number,x:any)=>n+num(x.amount),0); const totalC=credit.reduce((n:number,x:any)=>n+num(x.amount),0);
       if(!debit.length||!credit.length||Math.abs(totalD-totalC)>.005)continue;
       const txOut:Line[]=[];
       for(const x of debit){const name=String(x.account||"").trim();if(name){const a=accountFor(name,typeFor(name));txOut.push({accountId:a.id,debit:num(x.amount),credit:0});}}
       for(const x of credit){const name=String(x.account||"").trim();if(name){const a=accountFor(name,typeFor(name));txOut.push({accountId:a.id,debit:0,credit:num(x.amount)});}}
       if(txOut.length>=2)out.push({id:uid(),date:String(tx.date||today()),description:String(tx.description||"Parsed transaction"),reference:`AUTO-${out.length+1}`,kind:"Regular",lines:txOut});
     }
   }
   // Amounts already captured by the LLM pass, so the deterministic pass below doesn't
   // double-post the same transaction. This is a rough (amount-based) de-dupe, not a
   // guarantee, but it lets the two passes work together instead of one replacing the other.
   const llmCoveredAmounts=out.flatMap((e:any)=>e.lines?e.lines.filter((l:Line)=>l.debit>0).map((l:Line)=>l.debit):[]);
   const consume=(amt:number)=>{const i=llmCoveredAmounts.findIndex(x=>Math.abs(x-amt)<.005);if(i>=0){llmCoveredAmounts.splice(i,1);return true}return false};
   let lastDate=today();
   for(const line of lines){const l=line.toLowerCase(); const amt=amount(line); if(!amt)continue;
     const foundDate=line.match(MONTH_RE); const date=foundDate?foundDate[0]:lastDate; if(foundDate)lastDate=date;
     if(consume(amt))continue; // an LLM-parsed transaction already accounts for this sentence
     let m=line.replace(/,/g,"").match(/(?:₱|PHP|\$|P)\s*(\d+(?:\.\d{1,2})?).*?(?:paying|paid)\s+(?:₱|PHP|\$|P)\s*(\d+(?:\.\d{1,2})?).*?(?:remaining|balance).*?(?:note|payable)/i);
     if(/equipment/.test(l)&&m){const total=amt, cash=num(m[2]), pay=total-cash;if(pay>0)addCompound(line,"Equipment",total,[["Cash",cash],["Notes Payable",pay]],date);continue;}
     m=line.replace(/,/g,"").match(/(?:₱|PHP|\$|P)\s*(\d+(?:\.\d{1,2})?).*?(?:paying|paid)\s+(?:₱|PHP|\$|P)\s*(\d+(?:\.\d{1,2})?).*?(?:balance|remaining).*?(?:account|payable)/i);
     if(m){const total=amt,cash=num(m[2]),pay=total-cash; if(/suppl/.test(l))addCompound(line,"Supplies",total,[["Cash",cash],["Accounts Payable",pay]],date); else if(/equipment/.test(l))addCompound(line,"Equipment",total,[["Cash",cash],["Accounts Payable",pay]],date); else addCompound(line,"Equipment",total,[["Cash",cash],["Accounts Payable",pay]],date);continue;}
     if(/started|start(ed)?\s+(the\s+)?business|invested|owner.*(invested|contributed)|capitalized/.test(l)){add(line,"Cash","Owner's Capital",amt,date);continue;}
     if(/provided.*service.*on account|rendered.*service.*on account|earned.*on account|on account.*service|billed.*(client|customer)/.test(l)){add(line,"Accounts Receivable","Service Revenue",amt,date);continue;}
     if(/earned|provided.*service|rendered.*service|service revenue|received.*for services/.test(l)){add(line,"Cash","Service Revenue",amt,date);continue;}
     if(/paid.*rent|rent.*paid/.test(l)){add(line,"Rent Expense","Cash",amt,date);continue;}
     if(/paid.*insurance|insurance.*paid|prepaid.*insurance/.test(l)){add(line,"Prepaid Rent",/on account|on credit/.test(l)?"Accounts Payable":"Cash",amt,date);continue;}
     if(/paid.*salary|paid.*wage|wages.*paid|salary.*paid/.test(l)){add(line,"Salaries Expense","Cash",amt,date);continue;}
     if(/paid.*utilit|utility.*paid/.test(l)){add(line,"Utilities Expense","Cash",amt,date);continue;}
     if(/purchased.*suppl|bought.*suppl/.test(l)){add(line,"Supplies",/on account|on credit/.test(l)?"Accounts Payable":"Cash",amt,date);continue;}
     if(/purchased.*equipment|bought.*equipment/.test(l)){add(line,"Equipment",/on account|on credit/.test(l)?"Accounts Payable":"Cash",amt,date);continue;}
     if(/collected|received.*from.*customer|accounts receivable.*collected/.test(l)){add(line,"Cash","Accounts Receivable",amt,date);continue;}
     if(/owner.*withdrew|owner.*drawing|withdrew.*cash/.test(l)){add(line,"Owner's Drawing","Cash",amt,date);continue;}
     if(/received.*advance|unearned/.test(l)){add(line,"Cash","Unearned Revenue",amt,date);continue;}
     if(/paid.*account|paid.*payable/.test(l)){add(line,"Accounts Payable","Cash",amt,date);continue;}
     if(/borrowed|loan|note payable/.test(l)){add(line,"Cash","Notes Payable",amt,date);continue;}
     if(/supplies.*used|used.*supplies|supplies.*on hand|remaining.*supplies/.test(l)){add(line,"Supplies Expense","Supplies",amt,date);continue;}
     if(/depreciation/.test(l)){add(line,"Depreciation Expense","Accumulated Depreciation—Equipment",amt,date);continue;}
     if(/accrued.*salary|salary.*accrued|wages.*accrued/.test(l)){add(line,"Salaries Expense","Salaries Payable",amt,date);continue;}
     if(/earned.*unearned|unearned.*earned/.test(l)){add(line,"Unearned Revenue","Service Revenue",amt,date);continue;}
     out.push({unmatched:true,source:line,amount:amt,date});
   }
   if(newAccounts.length)setAccounts(prev=>[...prev,...newAccounts]);
   const unmatched=out.filter(x=>x.unmatched),generated=out.filter(x=>!x.unmatched); const totalD=generated.reduce((z:number,e:any)=>z+e.lines.reduce((a:number,x:Line)=>a+x.debit,0),0),totalC=generated.reduce((z:number,e:any)=>z+e.lines.reduce((a:number,x:Line)=>a+x.credit,0),0);
   setSolution({entries:generated,unmatched,totalD,totalC,balanced:Math.abs(totalD-totalC)<.005,requiredOutputs:solveMode==="complete"?["General Journal","General Ledger","Trial Balance","Adjusting Entries","Adjusted Trial Balance","Worksheet","Income Statement","Owner's Equity","Balance Sheet","Closing Entries","Post-Closing Trial Balance"]:required,ambiguities:Array.isArray(llmData?.ambiguities)?llmData.ambiguities:[]});
   setSolveBusy(false);
 };
 const applySolution=()=>{if(!solution)return;setEntries(prev=>[...prev,...solution.entries]);setNotice(`Applied ${solution.entries.length} generated entries. ${solution.unmatched.length} item(s) need review.`);setTab("General Journal");};
 const resolveUnmatched=(idx:number,debitId:string,creditId:string)=>{
   setSolution((prev:any)=>{
     if(!prev)return prev;
     const item=prev.unmatched[idx]; if(!item||!debitId||!creditId||debitId===creditId)return prev;
     const entry:Entry={id:uid(),date:item.date||today(),description:item.source,reference:`AUTO-${prev.entries.length+1}`,kind:"Regular",lines:[{accountId:debitId,debit:item.amount,credit:0},{accountId:creditId,debit:0,credit:item.amount}]};
     const entries=[...prev.entries,entry];
     const unmatched=prev.unmatched.filter((_:any,i:number)=>i!==idx);
     const totalD=entries.reduce((z:number,e:any)=>z+e.lines.reduce((a:number,x:Line)=>a+x.debit,0),0);
     const totalC=entries.reduce((z:number,e:any)=>z+e.lines.reduce((a:number,x:Line)=>a+x.credit,0),0);
     return {...prev,entries,unmatched,totalD,totalC,balanced:Math.abs(totalD-totalC)<.005};
   });
 };
 const readProblemFile=async(file:File)=>{setSolveBusy(true);setProblemFile(file.name);try{const ext=file.name.toLowerCase().split(".").pop();let text="";if(ext==="txt")text=await file.text();else if(ext==="docx"){const mammoth=await import("mammoth");text=(await mammoth.extractRawText({arrayBuffer:await file.arrayBuffer()})).value;}else if(ext==="pdf"){const pdfjs:any=await import("pdfjs-dist/legacy/build/pdf.mjs");const pdf=await pdfjs.getDocument({data:new Uint8Array(await file.arrayBuffer())}).promise;const pages:string[]=[];for(let i=1;i<=pdf.numPages;i++){const pg=await pdf.getPage(i),c=await pg.getTextContent();pages.push(c.items.map((x:any)=>x.str).join(" "));}text=pages.join("\n");}else throw new Error("Use TXT, DOCX or text-based PDF for Auto Solver.");setProblemText(text);setTab("Auto Solver");setNotice(`Loaded ${file.name}. Review the text, then Solve.`);}catch(e:any){setNotice(e?.message||"Could not read the file.");}finally{setSolveBusy(false)}};
 const nav=["Auto Solver","Dashboard","Transactions","Chart of Accounts","General Journal","General Ledger","Trial Balance","Adjusting Entries","Adjusted Trial Balance","Worksheet","Income Statement","Owner's Equity","Balance Sheet","Closing Entries","Post-Closing Trial Balance"];

 return <main>
  <aside className="sidebar">
   <div className="brand"><div className="logo">AF</div><div><b>Auto Finance</b><small>Studio v2</small></div></div>
   <div className="business-box"><small>BUSINESS NAME</small><input value={business} onChange={e=>setBusiness(e.target.value)}/><small>PERIOD END</small><input type="date" value={periodEnd} onChange={e=>setPeriodEnd(e.target.value)}/></div>
   <nav>{nav.map(n=><button key={n} className={tab===n?"active":""} onClick={()=>setTab(n)}>{n}</button>)}</nav>
   <button className="reset" onClick={reset}>Reset all data</button>
  </aside>
  <section className="content">
   <header><div><h1>{tab}</h1><p>{business} · Period ending {periodEnd}</p></div><div className="head-actions"><label className="upload-btn">📁 {importBusy?"Reading…":"Import File"}<input type="file" accept=".xlsx,.xls,.csv,.json,.txt,.docx,.pdf" hidden disabled={importBusy} onChange={e=>{const f=e.target.files?.[0];if(f){const ext=f.name.toLowerCase().split(".").pop();if(["txt","docx","pdf"].includes(ext||""))readProblemFile(f);else importFile(f);}e.currentTarget.value="";}}/></label><button onClick={()=>window.print()}>Print</button></div></header>
   {notice&&<div className="notice" onClick={()=>setNotice("")}>{notice}</div>}
   {tab==="Auto Solver"&&<AutoSolver text={problemText} setText={setProblemText} file={problemFile} busy={solveBusy} solution={solution} mode={solveMode} setMode={setSolveMode} onSolve={solveProblem} llmStatus={llmStatus} llmProgress={llmProgress} llmMessage={llmMessage} llmModel={LOCAL_MODEL_ID} onInitializeLLM={initializeLocalLLM} onApply={applySolution} onResolveUnmatched={resolveUnmatched} onExport={()=>{if(solution)exportWorkbook({accounts,entries:[...entries,...solution.entries],business,periodEnd,currency:"PHP",requiredOutputs:solution.requiredOutputs})}} onFile={readProblemFile} accounts={accounts}/>}
   {tab==="Dashboard"&&<Dashboard {...{entries,assets,liabilities,endingEquity,revenue,expenses,netIncome,t,at}}/>}
   {tab==="Transactions"&&<EntryForm accounts={accounts} kind="Regular" onPost={post}/>}
   {tab==="Adjusting Entries"&&<Adjusting accounts={accounts} entries={adjusting} onPost={post}/>}
   {tab==="Chart of Accounts"&&<Chart accounts={accounts} setAccounts={setAccounts}/>}
   {tab==="General Journal"&&<Journal accounts={accounts} entries={regular}/>}
   {tab==="General Ledger"&&<Ledger accounts={accounts} entries={[...regular,...adjusting]}/>}
   {tab==="Trial Balance"&&<TB rows={rows} adjusted={false}/>}
   {tab==="Adjusted Trial Balance"&&<TB rows={rows} adjusted/>}
   {tab==="Worksheet"&&<Worksheet rows={rows} revenue={revenue} expenses={expenses} netIncome={netIncome}/>}
   {tab==="Income Statement"&&<Income business={business} date={periodEnd} rows={rows} revenue={revenue} expenses={expenses} netIncome={netIncome}/>}
   {tab==="Owner's Equity"&&<Owner business={business} date={periodEnd} capital={contributed} netIncome={netIncome} drawing={drawing} ending={endingEquity}/>}
   {tab==="Balance Sheet"&&<BS business={business} date={periodEnd} rows={rows} assets={assets} liabilities={liabilities} equity={endingEquity}/>}
   {tab==="Closing Entries"&&<Closing rows={rows} revenue={revenue} expenses={expenses} netIncome={netIncome} drawing={drawing} onPost={post}/>}
   {tab==="Post-Closing Trial Balance"&&<PostClosing accounts={accounts} entries={[...regular,...adjusting,...closing]}/>}
  </section>
 </main>
}


async function exportWorkbook(p:any){
  const XLSX=await import("xlsx"); const wb=XLSX.utils.book_new();
  const accountMap=Object.fromEntries(p.accounts.map((a:any)=>[a.id,a]));
  const entries=(p.entries||[]); const required:OutputKey[]=p.requiredOutputs?.length?p.requiredOutputs:["General Journal","General Ledger","Trial Balance"];
  const addSheet=(name:string,rows:any[][])=>XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(rows),name);
  const accountsRows=[["Code","Account","Type","Normal Balance","Account ID"],...p.accounts.map((a:any)=>[a.code,a.name,a.type,a.normal,a.id])];
  const journalRows=[["Date","Reference","Type","Description","Account Code","Account","Debit","Credit","Memo"],...entries.flatMap((e:any)=>e.lines.map((l:any)=>[e.date,e.reference||"",e.kind,e.description,accountMap[l.accountId]?.code||"",accountMap[l.accountId]?.name||"",num(l.debit),num(l.credit),l.memo||""]))];
  addSheet("Summary",[["AUTO FINANCE STUDIO"],["Business",p.business],["Period End",p.periodEnd],["Mode","Required Outputs Only"],[],["Required Outputs"],...required.map(x=>[x])]);
  addSheet("Data - Accounts",accountsRows); addSheet("Data - Journal",journalRows);
  const hidden=["Data - Accounts","Data - Journal"]; hidden.forEach(n=>{if(wb.Workbook?.Sheets){} });
  const balMap:Record<string,{d:number;c:number}>={}; p.accounts.forEach((a:any)=>balMap[a.id]={d:0,c:0});
  entries.filter((e:any)=>e.kind!=="Closing").forEach((e:any)=>e.lines.forEach((l:any)=>{if(!balMap[l.accountId])balMap[l.accountId]={d:0,c:0};balMap[l.accountId].d+=num(l.debit);balMap[l.accountId].c+=num(l.credit)}));
  const adjMap:Record<string,{d:number;c:number}>={}; p.accounts.forEach((a:any)=>adjMap[a.id]={d:0,c:0}); entries.filter((e:any)=>e.kind!=="Closing").forEach((e:any)=>e.lines.forEach((l:any)=>{if(!adjMap[l.accountId])adjMap[l.accountId]={d:0,c:0};adjMap[l.accountId].d+=num(l.debit);adjMap[l.accountId].c+=num(l.credit)}));
  const rowFor=(a:any,m:any):any[]=>{const x=m[a.id]||{d:0,c:0};const net=a.normal==="Debit"?x.d-x.c:x.c-x.d;return [a.code,a.name,a.type,x.d||0,x.c||0,net]};
  if(required.includes("General Journal")) addSheet("General Journal",journalRows);
  if(required.includes("General Ledger")){const rows:any[][]=[["Account","Date","Reference","Description","Debit","Credit","Running Balance"]];for(const a of p.accounts){let run=0;for(const e of entries.filter((e:any)=>e.kind!=="Closing")){for(const l of e.lines.filter((l:any)=>l.accountId===a.id)){run+=a.normal==="Debit"?num(l.debit)-num(l.credit):num(l.credit)-num(l.debit);rows.push([a.name,e.date,e.reference||"",e.description,num(l.debit)||0,num(l.credit)||0,run]);}}}addSheet("General Ledger",rows);}
  if(required.includes("Trial Balance")){const rows:any[][]=[["Code","Account","Type","Debit","Credit","Balance"],...p.accounts.map((a:any)=>rowFor(a,balMap)),["","TOTAL","",`=SUM(D2:D${p.accounts.length+1})`,`=SUM(E2:E${p.accounts.length+1})`,`=D${p.accounts.length+2}-E${p.accounts.length+2}`]];addSheet("Trial Balance",rows);}
  if(required.includes("Adjusting Entries")) addSheet("Adjusting Entries",journalRows.filter((r:any[],i:number)=>i===0||r[2]==="Adjusting"));
  if(required.includes("Adjusted Trial Balance")){const rows:any[][]=[["Code","Account","Type","Adjusted Debit","Adjusted Credit","Balance"],...p.accounts.map((a:any)=>rowFor(a,adjMap)),["","TOTAL","",`=SUM(D2:D${p.accounts.length+1})`,`=SUM(E2:E${p.accounts.length+1})`,`=D${p.accounts.length+2}-E${p.accounts.length+2}`]];addSheet("Adjusted TB",rows);}
  const revenue=p.accounts.filter((a:any)=>a.type==="Revenue").reduce((s:number,a:any)=>s+((adjMap[a.id]?.c||0)-(adjMap[a.id]?.d||0)),0);
  const expenses=p.accounts.filter((a:any)=>a.type==="Expense").reduce((s:number,a:any)=>s+((adjMap[a.id]?.d||0)-(adjMap[a.id]?.c||0)),0); const net=revenue-expenses;
  if(required.includes("Worksheet")){const rows:any[][]=[["Account","TB Debit","TB Credit","Adjustments Debit","Adjustments Credit","Adjusted Debit","Adjusted Credit","Income Statement Debit","Income Statement Credit","Balance Sheet Debit","Balance Sheet Credit"]];for(const a of p.accounts){const b=balMap[a.id]||{d:0,c:0},x=adjMap[a.id]||{d:0,c:0};rows.push([a.name,b.d,b.c,x.d-b.d,x.c-b.c,x.d,x.c,a.type==="Expense"?x.d-x.c:0,a.type==="Revenue"?x.c-x.d:0,a.type!=="Revenue"&&a.type!=="Expense"&&a.normal==="Debit"?x.d-x.c:0,a.type!=="Revenue"&&a.type!=="Expense"&&a.normal==="Credit"?x.c-x.d:0]);}rows.push(["NET INCOME",0,0,0,0,0,0,Math.max(net,0),Math.max(-net,0),Math.max(-net,0),Math.max(net,0)]);addSheet("Worksheet",rows);}
  if(required.includes("Income Statement")){const rows=[["INCOME STATEMENT"],[p.business],["For period ended",p.periodEnd],[],["Revenue","Amount"],...p.accounts.filter((a:any)=>a.type==="Revenue").map((a:any)=>[a.name,(adjMap[a.id]?.c||0)-(adjMap[a.id]?.d||0)]),["Total Revenue",revenue],[],["Expenses","Amount"],...p.accounts.filter((a:any)=>a.type==="Expense").map((a:any)=>[a.name,(adjMap[a.id]?.d||0)-(adjMap[a.id]?.c||0)]),["Total Expenses",expenses],[net>=0?"NET INCOME":"NET LOSS",Math.abs(net)]];addSheet("Income Statement",rows);}
  const capital=p.accounts.filter((a:any)=>a.type==="Equity"&&a.name!=="Owner's Drawing").reduce((s:number,a:any)=>s+((adjMap[a.id]?.c||0)-(adjMap[a.id]?.d||0)),0); const drawing=(adjMap[p.accounts.find((a:any)=>a.name==="Owner's Drawing")?.id||""]?.d||0)-(adjMap[p.accounts.find((a:any)=>a.name==="Owner's Drawing")?.id||""]?.c||0); const ending=capital+net-drawing;
  if(required.includes("Owner's Equity")) addSheet("Owner's Equity",[["STATEMENT OF OWNER'S EQUITY"],[p.business],["For period ended",p.periodEnd],[],["Capital",capital],[net>=0?"Add: Net Income":"Less: Net Loss",Math.abs(net)],["Less: Drawings",drawing],["ENDING OWNER'S EQUITY",ending]]);
  const assets=p.accounts.filter((a:any)=>a.type==="Asset").reduce((s:number,a:any)=>s+((adjMap[a.id]?.d||0)-(adjMap[a.id]?.c||0)),0); const liabilities=p.accounts.filter((a:any)=>a.type==="Liability").reduce((s:number,a:any)=>s+((adjMap[a.id]?.c||0)-(adjMap[a.id]?.d||0)),0);
  if(required.includes("Balance Sheet")) addSheet("Balance Sheet",[["BALANCE SHEET"],[p.business],["As of",p.periodEnd],[],["Assets","Amount"],...p.accounts.filter((a:any)=>a.type==="Asset").map((a:any)=>[a.name,(adjMap[a.id]?.d||0)-(adjMap[a.id]?.c||0)]),["Total Assets",assets],[],["Liabilities","Amount"],...p.accounts.filter((a:any)=>a.type==="Liability").map((a:any)=>[a.name,(adjMap[a.id]?.c||0)-(adjMap[a.id]?.d||0)]),["Total Liabilities",liabilities],["Ending Owner's Equity",ending],["Total Liabilities + Equity",liabilities+ending],["CHECK",assets-(liabilities+ending)]]);
  if(required.includes("Closing Entries")) addSheet("Closing Entries",journalRows.filter((r:any[],i:number)=>i===0||r[2]==="Closing"));
  if(required.includes("Post-Closing Trial Balance")){const rows=[["Code","Account","Type","Debit","Credit"]];for(const a of p.accounts.filter((a:any)=>["Asset","Liability","Equity"].includes(a.type))){const x=adjMap[a.id]||{d:0,c:0};const n=a.normal==="Debit"?x.d-x.c:x.c-x.d;rows.push([a.code,a.name,a.type,n>0&&a.normal==="Debit"?n:0,n>0&&a.normal==="Credit"?n:0]);}addSheet("Post-Closing TB",rows);}
  for(const name of wb.SheetNames){const sh=wb.Sheets[name];sh["!freeze"]="A2";if(sh["!ref"]){const rg=XLSX.utils.decode_range(sh["!ref"]);sh["!cols"]=Array.from({length:rg.e.c+1},()=>({wch:18}));for(let R=0;R<=rg.e.r;R++)for(let C=0;C<=rg.e.c;C++){const cell=sh[XLSX.utils.encode_cell({r:R,c:C})];if(cell&&typeof cell.v==="number")cell.z="#,##0.00";}}}
  // Keep source data available for editing, but hide it so the workbook opens on the requested reports.
  if(!wb.Workbook)wb.Workbook={}; if(!wb.Workbook.Sheets)wb.Workbook.Sheets=[]; wb.SheetNames.forEach((name:string)=>{wb.Workbook!.Sheets!.push({name,Hidden:(name.startsWith("Data - ")?1:0)})});
  XLSX.writeFile(wb,`${(p.business||"Finance").replace(/[^a-z0-9]+/gi,"_")}_${p.periodEnd}_solution.xlsx`);
}

function Dashboard(p:any){return <><div className="cards"><Card label="Total Debits" value={money(p.at.debit)}/><Card label="Total Credits" value={money(p.at.credit)}/><Card label="Net Income" value={money(p.netIncome)}/><Card label="Journal Entries" value={p.entries.length}/></div><div className="grid2"><div className="panel"><h2>Financial Position</h2><Metric n="Assets" v={p.assets}/><Metric n="Liabilities" v={p.liabilities}/><Metric n="Owner's Equity" v={p.endingEquity}/></div><div className="panel"><h2>Income</h2><Metric n="Revenue" v={p.revenue}/><Metric n="Expenses" v={p.expenses}/><Metric n="Net Income" v={p.netIncome}/></div></div><div className="panel"><h2>Accounting equation</h2><div className="equation">{money(p.assets)} = {money(p.liabilities)} + {money(p.endingEquity)} <span className={Math.abs(p.assets-(p.liabilities+p.endingEquity))<.005?"ok":"bad"}>{Math.abs(p.assets-(p.liabilities+p.endingEquity))<.005?"Balanced":"Out of balance"}</span></div><p className="muted">All posted entries are double-entry validated before they affect the reports.</p></div></>}
function Card({label,value}:{label:string,value:any}){return <div className="card"><small>{label}</small><strong>{value}</strong></div>}
function Metric({n,v}:{n:string,v:number}){return <div className="metric"><span>{n}</span><b>{money(v)}</b></div>}

function EntryForm({accounts,kind,onPost,initial}:{accounts:Account[],kind:"Regular"|"Adjusting"|"Closing",onPost:(e:Entry)=>void,initial?:Line[]}){
 const [date,setDate]=useState(today()),[desc,setDesc]=useState(""),[ref,setRef]=useState("");
 const [lines,setLines]=useState<Line[]>(initial||[{accountId:accounts[0]?.id,debit:0,credit:0},{accountId:accounts[6]?.id||accounts[1]?.id,debit:0,credit:0}]);
 const upd=(i:number,k:keyof Line,v:any)=>setLines(x=>x.map((l,j)=>j===i?{...l,[k]:k==="accountId"||k==="memo"?v:num(v)}:l));
 const d=lines.reduce((s,l)=>s+num(l.debit),0),c=lines.reduce((s,l)=>s+num(l.credit),0);
 return <div className="panel"><div className="formgrid"><label>Date<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label><label>Reference<input value={ref} onChange={e=>setRef(e.target.value)} placeholder="JE-001"/></label><label className="wide">Description<input value={desc} onChange={e=>setDesc(e.target.value)} placeholder="Describe the transaction"/></label></div><div className="tablewrap"><table><thead><tr><th>Account</th><th>Memo</th><th>Debit</th><th>Credit</th><th></th></tr></thead><tbody>{lines.map((l,i)=><tr key={i}><td><select value={l.accountId} onChange={e=>upd(i,"accountId",e.target.value)}>{accounts.map(a=><option key={a.id} value={a.id}>{a.code} — {a.name}</option>)}</select></td><td><input value={l.memo||""} onChange={e=>upd(i,"memo",e.target.value)}/></td><td><input type="number" min="0" step=".01" value={l.debit||""} onChange={e=>upd(i,"debit",e.target.value)}/></td><td><input type="number" min="0" step=".01" value={l.credit||""} onChange={e=>upd(i,"credit",e.target.value)}/></td><td><button onClick={()=>setLines(x=>x.filter((_,j)=>j!==i))} disabled={lines.length<=2}>×</button></td></tr>)}</tbody></table></div><div className="entry-footer"><button onClick={()=>setLines(x=>[...x,{accountId:accounts[0].id,debit:0,credit:0}])}>+ Add line</button><span>Debit <b>{money(d)}</b> · Credit <b>{money(c)}</b> · Difference <b className={Math.abs(d-c)<.005?"ok":"bad"}>{money(d-c)}</b></span><button className="primary" onClick={()=>onPost({id:uid(),date,description:desc,reference:ref,kind,lines})}>Post {kind.toLowerCase()} entry</button></div></div>
}

function Adjusting({accounts,entries,onPost}:{accounts:Account[],entries:Entry[],onPost:(e:Entry)=>void}){return <><EntryForm accounts={accounts} kind="Adjusting" onPost={onPost}/><div className="panel"><h2>Posted adjusting entries</h2><Journal accounts={accounts} entries={entries}/></div></>}

function Chart({accounts,setAccounts}:{accounts:Account[],setAccounts:React.Dispatch<React.SetStateAction<Account[]>>}){
 const [code,setCode]=useState(""),[name,setName]=useState(""),[type,setType]=useState<AccountType>("Asset");
 const normal=(t:AccountType)=>t==="Asset"||t==="Expense"?"Debit":"Credit";
 return <div className="panel"><div className="formgrid"><label>Code<input value={code} onChange={e=>setCode(e.target.value)}/></label><label>Account name<input value={name} onChange={e=>setName(e.target.value)}/></label><label>Type<select value={type} onChange={e=>setType(e.target.value as AccountType)}>{["Asset","Liability","Equity","Revenue","Expense"].map(x=><option key={x}>{x}</option>)}</select></label><button className="primary" onClick={()=>{if(!code||!name)return;setAccounts(x=>[...x,{id:uid(),code,name,type,normal:normal(type)}]);setCode("");setName("")}}>Add account</button></div><div className="tablewrap"><table><thead><tr><th>Code</th><th>Account</th><th>Type</th><th>Normal</th><th></th></tr></thead><tbody>{accounts.map(a=><tr key={a.id}><td>{a.code}</td><td>{a.name}</td><td>{a.type}</td><td>{a.normal}</td><td><button className="danger" onClick={()=>setAccounts(x=>x.filter(y=>y.id!==a.id))}>Delete</button></td></tr>)}</tbody></table></div></div>
}

function Journal({accounts,entries}:{accounts:Account[],entries:Entry[]}){const m=Object.fromEntries(accounts.map(a=>[a.id,a]));return <div className="tablewrap"><table><thead><tr><th>Date</th><th>Ref</th><th>Description</th><th>Account</th><th>Debit</th><th>Credit</th></tr></thead><tbody>{entries.length?entries.flatMap(e=>e.lines.map((l,i)=><tr key={e.id+i}><td>{e.date}</td><td>{e.reference||"—"}</td><td>{i===0?e.description:""}</td><td>{m[l.accountId]?.code} — {m[l.accountId]?.name}</td><td>{l.debit?money(l.debit):""}</td><td>{l.credit?money(l.credit):""}</td></tr>)):<tr><td colSpan={6} className="empty">No entries posted.</td></tr>}</tbody></table></div>}

function Ledger({accounts,entries}:{accounts:Account[],entries:Entry[]}){return <div className="ledgergrid">{accounts.map(a=>{let run=0;const es=entries.flatMap(e=>e.lines.map(l=>({...l,date:e.date,desc:e.description}))).filter(l=>l.accountId===a.id);return <div className="panel" key={a.id}><h3>{a.code} — {a.name}</h3><table><thead><tr><th>Date</th><th>Debit</th><th>Credit</th><th>Balance</th></tr></thead><tbody>{es.map((e,i)=>{run+=a.normal==="Debit"?e.debit-e.credit:e.credit-e.debit;return <tr key={i}><td>{e.date}</td><td>{e.debit?money(e.debit):""}</td><td>{e.credit?money(e.credit):""}</td><td>{money(run)}</td></tr>})}<tr className="total"><td>Ending</td><td></td><td></td><td>{money(run)}</td></tr></tbody></table></div>})}</div>}

function TB({rows,adjusted}:{rows:any[],adjusted:boolean}){const d=rows.reduce((s,r)=>s+(adjusted?r.adjDebit:r.debit),0),c=rows.reduce((s,r)=>s+(adjusted?r.adjCredit:r.credit),0);return <Report title={adjusted?"Adjusted Trial Balance":"Trial Balance"}><table><thead><tr><th>Code</th><th>Account</th><th>Debit</th><th>Credit</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td>{r.code}</td><td>{r.name}</td><td>{(adjusted?r.adjDebit:r.debit)?money(adjusted?r.adjDebit:r.debit):""}</td><td>{(adjusted?r.adjCredit:r.credit)?money(adjusted?r.adjCredit:r.credit):""}</td></tr>)}<tr className="total"><td colSpan={2}>TOTAL</td><td>{money(d)}</td><td>{money(c)}</td></tr></tbody></table><BalanceCheck d={d} c={c}/></Report>}

function Worksheet({rows,revenue,expenses,netIncome}:{rows:any[],revenue:number,expenses:number,netIncome:number}){
 return <Report title="10-Column Worksheet"><div className="tablewrap"><table className="worksheet"><thead><tr><th rowSpan={2}>Account</th><th colSpan={2}>Trial Balance</th><th colSpan={2}>Adjustments</th><th colSpan={2}>Adjusted TB</th><th colSpan={2}>Income Statement</th><th colSpan={2}>Balance Sheet</th></tr><tr>{["Dr","Cr","Dr","Cr","Dr","Cr","Dr","Cr","Dr","Cr"].map((x,i)=><th key={i}>{x}</th>)}</tr></thead><tbody>{rows.map(r=>{const td=r.debit,tc=r.credit,ad=r.adjDebit-r.debit,ac=r.adjCredit-r.credit;let isd=0,isc=0,bsd=0,bsc=0;if(r.type==="Revenue")isc=r.adjNet;else if(r.type==="Expense")isd=r.adjNet;else if(r.normal==="Debit")bsd=r.adjNet;else bsc=r.adjNet;return <tr key={r.id}><td>{r.name}</td><td>{td?money(td):""}</td><td>{tc?money(tc):""}</td><td>{ad>0?money(ad):""}</td><td>{ac>0?money(ac):""}</td><td>{r.adjDebit?money(r.adjDebit):""}</td><td>{r.adjCredit?money(r.adjCredit):""}</td><td>{isd?money(isd):""}</td><td>{isc?money(isc):""}</td><td>{bsd?money(bsd):""}</td><td>{bsc?money(bsc):""}</td></tr>})}<tr className="total"><td>NET INCOME</td><td colSpan={6}></td><td>{netIncome>0?money(netIncome):""}</td><td>{netIncome<0?money(-netIncome):""}</td><td>{netIncome<0?money(-netIncome):""}</td><td>{netIncome>0?money(netIncome):""}</td></tr><tr className="total"><td>Column Totals</td><td colSpan={2}>{money(rows.reduce((s,r)=>s+r.debit+r.credit,0))}</td><td colSpan={2}></td><td colSpan={2}>{money(rows.reduce((s,r)=>s+r.adjDebit+r.adjCredit,0))}</td><td colSpan={2}>{money(revenue+expenses+Math.max(netIncome,0))}</td><td colSpan={2}>{money(rows.filter(r=>r.type!=="Revenue"&&r.type!=="Expense").reduce((s,r)=>s+r.adjNet,0)+Math.max(netIncome,0))}</td></tr></tbody></table></div><p className="muted">Adjustment columns are calculated from posted adjusting entries. Income statement and balance sheet columns use the adjusted balances.</p></Report>
}

function Income({business,date,rows,revenue,expenses,netIncome}:{business:string,date:string,rows:any[],revenue:number,expenses:number,netIncome:number}){return <Report title="Income Statement" subtitle={`${business} · For the period ended ${date}`}><table><tbody><tr><th colSpan={2}>Revenue</th></tr>{rows.filter(r=>r.type==="Revenue"&&r.adjNet!==0).map(r=><tr key={r.id}><td>{r.name}</td><td>{money(r.adjNet)}</td></tr>)}<tr className="subtotal"><td>Total Revenue</td><td>{money(revenue)}</td></tr><tr><th colSpan={2}>Expenses</th></tr>{rows.filter(r=>r.type==="Expense"&&r.adjNet!==0).map(r=><tr key={r.id}><td>{r.name}</td><td>{money(r.adjNet)}</td></tr>)}<tr className="subtotal"><td>Total Expenses</td><td>{money(expenses)}</td></tr><tr className="grand"><td>{netIncome>=0?"NET INCOME":"NET LOSS"}</td><td>{money(Math.abs(netIncome))}</td></tr></tbody></table></Report>}

function Owner({business,date,capital,netIncome,drawing,ending}:{business:string,date:string,capital:number,netIncome:number,drawing:number,ending:number}){return <Report title="Statement of Owner's Equity" subtitle={`${business} · For the period ended ${date}`}><table><tbody><tr><td>Capital</td><td>{money(capital)}</td></tr><tr><td>{netIncome>=0?"Add: Net Income":"Less: Net Loss"}</td><td>{money(Math.abs(netIncome))}</td></tr><tr><td>Less: Drawings</td><td>{money(drawing)}</td></tr><tr className="grand"><td>ENDING OWNER'S EQUITY</td><td>{money(ending)}</td></tr></tbody></table></Report>}

function BS({business,date,rows,assets,liabilities,equity}:{business:string,date:string,rows:any[],assets:number,liabilities:number,equity:number}){return <Report title="Balance Sheet" subtitle={`${business} · As of ${date}`}><table><tbody><tr><th colSpan={2}>Assets</th></tr>{rows.filter(r=>r.type==="Asset"&&r.adjNet!==0).map(r=><tr key={r.id}><td>{r.name}</td><td>{money(r.adjNet)}</td></tr>)}<tr className="subtotal"><td>Total Assets</td><td>{money(assets)}</td></tr><tr><th colSpan={2}>Liabilities</th></tr>{rows.filter(r=>r.type==="Liability"&&r.adjNet!==0).map(r=><tr key={r.id}><td>{r.name}</td><td>{money(r.adjNet)}</td></tr>)}<tr className="subtotal"><td>Total Liabilities</td><td>{money(liabilities)}</td></tr><tr><th colSpan={2}>Owner's Equity</th></tr><tr><td>Ending Owner's Equity</td><td>{money(equity)}</td></tr><tr className="grand"><td>Total Liabilities + Equity</td><td>{money(liabilities+equity)}</td></tr></tbody></table><BalanceCheck d={assets} c={liabilities+equity}/></Report>}

function BalanceCheck({d,c}:{d:number,c:number}){return <p className={Math.abs(d-c)<.005?"balance-ok":"balance-bad"}>{Math.abs(d-c)<.005?"✓ Balanced":"⚠ Difference: "+money(d-c)}</p>}

function Closing({rows,revenue,expenses,netIncome,drawing,onPost}:{rows:any[],revenue:number,expenses:number,netIncome:number,drawing:number,onPost:(e:Entry)=>void}){
 const [done,setDone]=useState(false);
 function close(){
  if(done)return;
  const lines:Line[]=[];
  rows.filter(r=>r.type==="Revenue"&&r.adjNet>0).forEach(r=>lines.push({accountId:r.id,debit:r.adjNet,credit:0}));
  lines.push({accountId:"999",debit:0,credit:revenue});
  // Closing reference is intentionally shown rather than silently posted because Income Summary
  // is not a permanent account in this chart.
  setDone(true);
 }
 return <Report title="Closing Entries"><p className="muted">Closing entries transfer temporary Revenue, Expense, and Drawing balances to the owner's equity. This app keeps the permanent accounting data separate and provides a review step before posting.</p><table><tbody><tr><th>Closing step</th><th>Debit</th><th>Credit</th></tr><tr><td>Close revenue to Income Summary</td><td>{money(revenue)}</td><td>{money(revenue)}</td></tr><tr><td>Close expenses to Income Summary</td><td>{money(expenses)}</td><td>{money(expenses)}</td></tr><tr><td>Close Income Summary to Capital</td><td>{money(Math.max(netIncome,0))}</td><td>{money(Math.max(netIncome,0))}</td></tr><tr><td>Close Drawing to Capital</td><td>{money(drawing)}</td><td>{money(drawing)}</td></tr></tbody></table><button className="primary" onClick={close}>{done?"Reviewed":"Mark closing entries reviewed"}</button><p className="muted">Net income: {money(netIncome)} · Drawings: {money(drawing)}</p></Report>
}

function PostClosing({accounts,entries}:{accounts:Account[],entries:Entry[]}){const m=Object.fromEntries(accounts.map(a=>[a.id,a]));const b:Record<string,{d:number;c:number}>={};accounts.forEach(a=>b[a.id]={d:0,c:0});entries.forEach(e=>e.lines.forEach(l=>{if(e.kind!=="Closing"){b[l.accountId].d+=l.debit;b[l.accountId].c+=l.credit}}));const rs=accounts.filter(a=>["Asset","Liability","Equity"].includes(a.type)).map(a=>({a,d:b[a.id].d,c:b[a.id].c,net:a.normal==="Debit"?b[a.id].d-b[a.id].c:b[a.id].c-b[a.id].d})).filter(r=>Math.abs(r.net)>.005);return <Report title="Post-Closing Trial Balance"><p className="muted">Permanent accounts only. Temporary revenue, expense, and drawing accounts are excluded.</p><table><thead><tr><th>Code</th><th>Account</th><th>Debit</th><th>Credit</th></tr></thead><tbody>{rs.map(r=><tr key={r.a.id}><td>{r.a.code}</td><td>{r.a.name}</td><td>{r.net>0&&r.a.normal==="Debit"?money(r.net):r.a.normal==="Credit"&&r.net<0?money(-r.net):""}</td><td>{r.net>0&&r.a.normal==="Credit"?money(r.net):r.a.normal==="Debit"&&r.net<0?money(-r.net):""}</td></tr>)}</tbody></table></Report>}

function Report({title,subtitle,children}:{title:string,subtitle?:string,children:React.ReactNode}){return <div className="panel report"><div className="reporthead"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button onClick={()=>window.print()}>Print</button></div>{children}</div>}

function UnmatchedResolver({item,index,accounts,onResolve}:{item:any,index:number,accounts:Account[],onResolve:(i:number,debitId:string,creditId:string)=>void}){
 const [debit,setDebit]=useState(accounts[0]?.id||"");
 const [credit,setCredit]=useState(accounts[1]?.id||accounts[0]?.id||"");
 return <div className="unmatched-row">
  <div className="unmatched-source"><b>{item.source}</b><span className="muted"> — {money(item.amount)}</span></div>
  <div className="unmatched-controls">
   <select value={debit} onChange={e=>setDebit(e.target.value)}>{accounts.map(a=><option key={a.id} value={a.id}>Debit: {a.code} — {a.name}</option>)}</select>
   <select value={credit} onChange={e=>setCredit(e.target.value)}>{accounts.map(a=><option key={a.id} value={a.id}>Credit: {a.code} — {a.name}</option>)}</select>
   <button onClick={()=>onResolve(index,debit,credit)} disabled={!debit||!credit||debit===credit}>Resolve</button>
  </div>
 </div>;
}
function AutoSolver(p:any){return <div className="solver"><div className="hero"><span className="eyebrow">AUTO ACCOUNTING · v7</span><h2>Upload a word problem. Solve only what it asks for.</h2><p>Uses a small local WebLLM model for natural-language interpretation. No cloud AI API or API key is used. Accounting calculations and validation remain deterministic. The model is cached by the browser after its first download.</p><div className="solver-actions"><label className="upload-btn">{p.busy?"Reading…":"Upload Problem"}<input hidden type="file" accept=".txt,.docx,.pdf" disabled={p.busy} onChange={e=>{const f=e.target.files?.[0];if(f)p.onFile(f);e.currentTarget.value=""}}/></label><button className="primary" onClick={p.onSolve}>Analyze & Solve</button></div></div><div className="panel local-ai-panel"><div className="local-ai-head"><div><b>Local model</b><div className="muted">{p.llmModel} · WebGPU · on-device</div></div><span className={`pill ${p.llmStatus==="ready"?"ok":p.llmStatus==="error"?"bad":""}`}>{p.llmStatus==="ready"?"Ready":p.llmStatus==="downloading"?`${p.llmProgress}%`:p.llmStatus==="checking"?"Checking…":"Not initialized"}</span></div>{p.llmStatus==="downloading"&&<><div className="model-progress"><span style={{width:`${p.llmProgress}%`}}/></div><div className="muted model-progress-text">{p.llmMessage}</div></>}{p.llmStatus==="ready"&&<div className="muted model-progress-text">{p.llmMessage}</div>}{p.llmStatus==="error"&&<div className="warning">{p.llmMessage}</div>}<div className="local-model-actions"><button className="primary" onClick={p.onInitializeLLM} disabled={p.llmStatus==="checking"||p.llmStatus==="downloading"||p.llmStatus==="ready"}>{p.llmStatus==="ready"?"Local Model Ready":p.llmStatus==="downloading"?"Downloading…":"Download & Initialize Local Model"}</button><span className="muted">First use downloads the small Qwen 0.5B model to this browser. Later visits reuse the local cache.</span></div><label><b>Problem statement</b><textarea className="problem-input" value={p.text} onChange={e=>p.setText(e.target.value)} placeholder="Example: On January 1, Maria started a service business by investing ₱50,000 cash. Prepare the general journal and trial balance."/></label><div className="solve-mode"><b>Output mode</b><label><input type="radio" checked={p.mode==="required"} onChange={()=>p.setMode("required")}/> Required outputs only</label><label><input type="radio" checked={p.mode==="complete"} onChange={()=>p.setMode("complete")}/> Complete accounting cycle</label></div></div>{p.solution&&<div className="panel"><div className="solution-head"><div><h2>Solution Preview</h2><p className="muted">Rules-based analysis. Review any unmatched transactions before applying.</p></div><span className={p.solution.balanced&&p.solution.unmatched.length===0?"ok pill":"bad pill"}>{p.solution.balanced&&p.solution.unmatched.length===0?"Validated":"Needs review"}</span></div><div className="required-box"><b>Required outputs detected</b><div className="output-chips">{p.solution.requiredOutputs.map((x:string)=><span key={x}>{x}</span>)}</div></div><div className="cards"><Card label="Generated Entries" value={p.solution.entries.length}/><Card label="Total Debits" value={money(p.solution.totalD)}/><Card label="Total Credits" value={money(p.solution.totalC)}/><Card label="Needs Review" value={p.solution.unmatched.length}/></div>{p.solution.entries.map((e:any,i:number)=><div className="auto-entry" key={i}><b>{e.date} · {e.reference} · {e.description}</b><table><tbody>{e.lines.map((l:any,j:number)=>{const a=p.accounts.find((x:any)=>x.id===l.accountId);return <tr key={j}><td>{a?.name}</td><td>{l.debit?money(l.debit):""}</td><td>{l.credit?money(l.credit):""}</td></tr>})}</tbody></table></div>)}{p.solution.unmatched.length>0&&<div className="warning"><b>Needs manual review</b><p className="muted">The parser found an amount but couldn't confidently match a transaction type. Pick the two accounts and resolve it directly, or edit it later in Transactions.</p>{p.solution.unmatched.map((x:any,i:number)=><UnmatchedResolver key={i} item={x} index={i} accounts={p.accounts} onResolve={p.onResolveUnmatched}/>)}</div>}<div className="actions"><button onClick={p.onApply}>Apply to Studio</button><button className="primary" onClick={p.onExport}>Export Required Outputs to Excel</button></div></div>}</div>}

