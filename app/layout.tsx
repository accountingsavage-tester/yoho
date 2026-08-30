import type { Metadata } from "next";
import "./globals.css";
import "./ai.css";
import "./glass.css";
import "./ai/v9.css";

export const metadata: Metadata = {
  title: "Yoho v9 — AI Accounting Engine",
  description: "Fast hybrid accounting automation with deterministic validation and local WebLLM"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
