import Script from "next/script";
import type { ReactNode } from "react";

export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Script
        id="studio-ai-experience"
        strategy="afterInteractive"
        dangerouslySetInnerHTML={{
          __html: `
(function () {
  var TAB_KEY = "afs-active-studio-tab";
  var NAV = [
    "Auto Solver", "Dashboard", "Transactions", "Chart of Accounts",
    "General Journal", "General Ledger", "Trial Balance", "Adjusting Entries",
    "Adjusted Trial Balance", "Worksheet", "Income Statement", "Owner's Equity",
    "Balance Sheet", "Closing Entries", "Post-Closing Trial Balance"
  ];
  var normalize = function (text) { return String(text || "").replace(/\\s+/g, " ").trim(); };
  var findButton = function (tab) {
    return Array.prototype.slice.call(document.querySelectorAll(".sidebar nav button")).find(function (b) { return normalize(b.textContent) === tab; });
  };

  /* Keep the current Studio section after refresh. */
  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var button = target.closest(".sidebar nav button");
    if (!button) return;
    var tab = normalize(button.textContent);
    if (NAV.indexOf(tab) !== -1) { try { localStorage.setItem(TAB_KEY, tab); } catch (_) {} }
  }, true);
  function restore() {
    var saved = null;
    try { saved = localStorage.getItem(TAB_KEY); } catch (_) {}
    if (!saved || NAV.indexOf(saved) === -1) return;
    var button = findButton(saved);
    if (button && !button.classList.contains("active")) button.click();
  }
  var attempts = 0;
  function retryRestore() { restore(); attempts += 1; if (attempts < 30) window.setTimeout(retryRestore, 100); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", retryRestore, { once: true }); else retryRestore();

  /* Glass AI Assistant launcher. It is intentionally independent from the accounting engine. */
  function mountAssistant() {
    if (document.getElementById("yoho-ai-fab")) return;
    var fab = document.createElement("a");
    fab.id = "yoho-ai-fab";
    fab.href = "/ai";
    fab.setAttribute("aria-label", "Open AI Accounting Assistant");
    fab.innerHTML = '<span class="yoho-ai-spark">✦</span><span class="yoho-ai-label">AI Assistant</span>';
    var style = document.createElement("style");
    style.textContent = `
      #yoho-ai-fab{position:fixed;right:22px;bottom:22px;z-index:9999;display:flex;align-items:center;gap:9px;padding:12px 16px;border:1px solid rgba(255,255,255,.55);border-radius:999px;color:#fff;text-decoration:none;font:700 13px/1 system-ui,sans-serif;background:linear-gradient(135deg,rgba(17,24,39,.92),rgba(51,65,85,.82));box-shadow:0 14px 40px rgba(15,23,42,.24),inset 0 1px rgba(255,255,255,.2);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);transition:transform .2s,box-shadow .2s}#yoho-ai-fab:hover{transform:translateY(-2px);box-shadow:0 18px 48px rgba(15,23,42,.3),inset 0 1px rgba(255,255,255,.25)}.yoho-ai-spark{font-size:16px}.yoho-ai-label{white-space:nowrap}@media(max-width:600px){#yoho-ai-fab{right:14px;bottom:calc(14px + env(safe-area-inset-bottom));padding:12px 14px}.yoho-ai-label{display:none}}
    `;
    document.head.appendChild(style);
    document.body.appendChild(fab);
  }

  /* Non-blocking visual feedback around the existing solver. We do not replace its v7 logic. */
  function mountSolverActivity() {
    if (document.getElementById("yoho-solver-activity")) return;
    var box = document.createElement("div");
    box.id = "yoho-solver-activity";
    box.innerHTML = '<div class="yoho-solver-card"><div class="yoho-spinner"></div><div><b id="yoho-solver-title">Analyzing accounting problem</b><span id="yoho-solver-step">Preparing the AI reasoning pipeline…</span></div><button id="yoho-solver-hide" aria-label="Hide progress">×</button></div>';
    var style = document.createElement("style");
    style.textContent = `
      #yoho-solver-activity{position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:9998;display:none;width:min(520px,calc(100vw - 28px));pointer-events:none}.yoho-solver-card{pointer-events:auto;display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:14px 16px;border:1px solid rgba(255,255,255,.6);border-radius:16px;background:rgba(255,255,255,.76);box-shadow:0 16px 50px rgba(15,23,42,.15);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);font:13px/1.35 system-ui,sans-serif;color:#172033}.yoho-solver-card b{display:block}.yoho-solver-card span{display:block;margin-top:3px;color:#64748b;font-size:12px}.yoho-spinner{width:22px;height:22px;border:2px solid rgba(15,23,42,.15);border-top-color:#111827;border-radius:50%;animation:yoho-spin .75s linear infinite}@keyframes yoho-spin{to{transform:rotate(360deg)}}#yoho-solver-hide{border:0;background:transparent;font-size:22px;color:#64748b;cursor:pointer}.yoho-solver-card.done .yoho-spinner{animation:none;border-color:#16a34a;background:#16a34a}.yoho-solver-card.done .yoho-spinner:after{content:'✓';display:block;color:#fff;font-size:13px;text-align:center;line-height:18px}
    `;
    document.head.appendChild(style); document.body.appendChild(box);
    document.getElementById("yoho-solver-hide").addEventListener("click", function(){ box.style.display="none"; });
  }
  function showActivity() {
    var root=document.getElementById("yoho-solver-activity"); if(!root)return;
    root.style.display="block"; root.querySelector(".yoho-solver-card").classList.remove("done");
    var step=root.querySelector("#yoho-solver-step"), title=root.querySelector("#yoho-solver-title");
    var steps=["Reading the accounting problem…","Identifying transactions and accounts…","Determining debit and credit treatment…","Building the journal entry…","Validating that debits equal credits…","Preparing the requested outputs…"];
    var i=0; var timer=window.setInterval(function(){ if(i<steps.length-1){i++;step.textContent=steps[i];} },900);
    root.dataset.timer=String(timer); root.dataset.started="1"; root._finish=function(){window.clearInterval(timer);step.textContent="Validation complete — review the generated solution.";title.textContent="Accounting problem solved";root.querySelector(".yoho-solver-card").classList.add("done");window.setTimeout(function(){root.style.display="none"},1800);};
  }
  function finishActivity(){var root=document.getElementById("yoho-solver-activity");if(root&&root._finish)root._finish();}
  function watchSolver(){
    document.addEventListener("click",function(event){
      var target=event.target; if(!target||!target.closest)return;
      var button=target.closest("button"); if(!button)return;
      var text=normalize(button.textContent).toLowerCase();
      if(/solve|analyze|generate/.test(text) && !/clear|reset|download|export/.test(text)){
        window.setTimeout(function(){
          if(button.disabled){showActivity(); var checks=0; var timer=window.setInterval(function(){checks++; if(!button.disabled||checks>240){window.clearInterval(timer); if(button.disabled)finishActivity(); else finishActivity();}},250);}
        },30);
      }
    },true);
  }
  function boot(){mountAssistant();mountSolverActivity();watchSolver();}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();`,
        }}
      />
      {children}
    </>
  );
}
