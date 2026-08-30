import Script from "next/script";
import type { ReactNode } from "react";

export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Script
        id="studio-ai-experience"
        strategy="afterInteractive"
        dangerouslySetInnerHTML={{
          __html: `(function(){
  var KEY="afs-active-studio-tab";
  var NAV=["Auto Solver","Dashboard","Transactions","Chart of Accounts","General Journal","General Ledger","Trial Balance","Adjusting Entries","Adjusted Trial Balance","Worksheet","Income Statement","Owner's Equity","Balance Sheet","Closing Entries","Post-Closing Trial Balance"];
  function norm(x){return String(x||"").replace(/\\s+/g," ").trim();}
  function restore(){var s=null;try{s=localStorage.getItem(KEY)}catch(e){}if(!s||NAV.indexOf(s)<0)return;var bs=document.querySelectorAll(".sidebar nav button");for(var i=0;i<bs.length;i++){if(norm(bs[i].textContent)===s&&!bs[i].classList.contains("active")){bs[i].click();break}}}
  document.addEventListener("click",function(e){var t=e.target;if(!t||!t.closest)return;var b=t.closest(".sidebar nav button");if(!b)return;var s=norm(b.textContent);if(NAV.indexOf(s)>=0){try{localStorage.setItem(KEY,s)}catch(x){}}},true);
  function assistant(){if(document.getElementById("yoho-ai-fab"))return;var a=document.createElement("a");a.id="yoho-ai-fab";a.href="/ai";a.setAttribute("aria-label","Open AI Accounting Assistant");a.textContent="✦ AI Assistant";var st=document.createElement("style");st.textContent="#yoho-ai-fab{position:fixed;right:22px;bottom:22px;z-index:9999;padding:12px 16px;border:1px solid rgba(255,255,255,.55);border-radius:999px;color:#fff;text-decoration:none;font:700 13px system-ui;background:rgba(17,24,39,.9);box-shadow:0 14px 40px rgba(15,23,42,.24);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}#yoho-ai-fab:hover{transform:translateY(-2px)}@media(max-width:600px){#yoho-ai-fab{right:14px;bottom:calc(14px + env(safe-area-inset-bottom));padding:12px 14px}}";document.head.appendChild(st);document.body.appendChild(a)}
  function progress(){if(document.getElementById("yoho-solver-activity"))return;var b=document.createElement("div");b.id="yoho-solver-activity";b.innerHTML='<div class="yoho-solver-card"><div class="yoho-spinner"></div><div><b id="yoho-solver-title">Analyzing accounting problem</b><span id="yoho-solver-step">Preparing the AI reasoning pipeline...</span></div><button id="yoho-solver-hide" aria-label="Hide progress">×</button></div>';var st=document.createElement("style");st.textContent="#yoho-solver-activity{position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:9998;display:none;width:min(520px,calc(100vw - 28px))}.yoho-solver-card{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:14px 16px;border:1px solid rgba(255,255,255,.6);border-radius:16px;background:rgba(255,255,255,.8);box-shadow:0 16px 50px rgba(15,23,42,.15);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);font:13px/1.35 system-ui;color:#172033}.yoho-solver-card b,.yoho-solver-card span{display:block}.yoho-solver-card span{margin-top:3px;color:#64748b;font-size:12px}.yoho-spinner{width:22px;height:22px;border:2px solid rgba(15,23,42,.15);border-top-color:#111827;border-radius:50%;animation:yoho-spin .75s linear infinite}@keyframes yoho-spin{to{transform:rotate(360deg)}}#yoho-solver-hide{border:0;background:transparent;font-size:22px;color:#64748b;cursor:pointer}";document.head.appendChild(st);document.body.appendChild(b);document.getElementById("yoho-solver-hide").onclick=function(){b.style.display="none"};}
  function watch(){document.addEventListener("click",function(e){var t=e.target;if(!t||!t.closest)return;var b=t.closest("button");if(!b)return;var x=norm(b.textContent).toLowerCase();if(!/solve|analyze|generate/.test(x)||/clear|reset|download|export/.test(x))return;var box=document.getElementById("yoho-solver-activity");if(!box)return;box.style.display="block";var step=box.querySelector("#yoho-solver-step"),title=box.querySelector("#yoho-solver-title"),steps=["Reading the accounting problem...","Identifying transactions and accounts...","Determining debit and credit treatment...","Building the journal entry...","Validating that debits equal credits...","Preparing the requested outputs..."];var i=0;var timer=setInterval(function(){i++;if(i<steps.length)step.textContent=steps[i];else clearInterval(timer)},900);setTimeout(function(){clearInterval(timer);step.textContent="Review the generated solution.";title.textContent="Accounting analysis complete";setTimeout(function(){box.style.display="none"},1600)},6000)},true)}
  function boot(){assistant();progress();watch();restore();var n=0;var r=setInterval(function(){restore();if(++n>30)clearInterval(r)},100)}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})()`
        }}
      />
      {children}
    </>
  );
}
