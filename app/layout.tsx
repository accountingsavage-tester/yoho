import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Auto Finance Studio",
  description: "Automated double-entry accounting and financial statements"
};

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
