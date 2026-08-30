import type { Metadata } from "next";
import "./globals.css";
import "./ai.css";
import "./glass.css";
import "./landing-v9.css";
import "./ui-navigation.css";
import "./yoho-theme.css";
import BackButton from "./BackButton";

export const metadata: Metadata = { title: "YOHO · Accounting Intelligence", description: "AI-assisted double-entry accounting and financial statements" };

export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}<BackButton /></body></html>; }
