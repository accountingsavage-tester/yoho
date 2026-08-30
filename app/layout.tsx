import type { Metadata } from "next";
import "./globals.css";
import "./ai.css";
import "./glass.css";

export const metadata: Metadata = {
  title: "Auto Finance Studio",
  description: "AI-assisted double-entry accounting and financial statements"
};

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}