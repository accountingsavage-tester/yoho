import Script from "next/script";
import type { ReactNode } from "react";

export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Script
        id="studio-tab-persistence"
        strategy="afterInteractive"
        dangerouslySetInnerHTML={{
          __html: `
(function () {
  var KEY = "afs-active-studio-tab";
  var NAV = [
    "Auto Solver", "Dashboard", "Transactions", "Chart of Accounts",
    "General Journal", "General Ledger", "Trial Balance", "Adjusting Entries",
    "Adjusted Trial Balance", "Worksheet", "Income Statement", "Owner's Equity",
    "Balance Sheet", "Closing Entries", "Post-Closing Trial Balance"
  ];

  function normalize(text) {
    return String(text || "").replace(/\\s+/g, " ").trim();
  }

  function findButton(tab) {
    var buttons = Array.prototype.slice.call(document.querySelectorAll(".sidebar nav button"));
    return buttons.find(function (button) { return normalize(button.textContent) === tab; });
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var button = target.closest(".sidebar nav button");
    if (!button) return;
    var tab = normalize(button.textContent);
    if (NAV.indexOf(tab) !== -1) {
      try { localStorage.setItem(KEY, tab); } catch (_) {}
    }
  }, true);

  function restore() {
    var saved = null;
    try { saved = localStorage.getItem(KEY); } catch (_) {}
    if (!saved || NAV.indexOf(saved) === -1) return;
    var button = findButton(saved);
    if (button && !button.classList.contains("active")) {
      button.click();
    }
  }

  var attempts = 0;
  function retryRestore() {
    restore();
    attempts += 1;
    if (attempts < 20) window.setTimeout(retryRestore, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", retryRestore, { once: true });
  } else {
    retryRestore();
  }
})();`,
        }}
      />
      {children}
    </>
  );
}
