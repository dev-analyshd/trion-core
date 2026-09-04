import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { CHAIN_COUNT, VM_FAMILY_COUNT } from "@/lib/trion/client";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TRION Protocol — Behavioral Truth Infrastructure",
  description:
    `Institutional dashboard for the TRION Protocol and BTCP Zero-Bridge: five-plane coherence C(t), master equation T(t), DW-BFT consensus, ${CHAIN_COUNT} chains across ${VM_FAMILY_COUNT} VM families, live behavioral hash streams.`,
  keywords: [
    "TRION",
    "BTCP",
    "zero-bridge",
    "behavioral truth",
    "coherence",
    "DW-BFT",
    "HashDNA",
    "cross-chain",
  ],
  authors: [{ name: "dev-analyshd" }],
  icons: {
    icon: "https://z-cdn.chatglm.cn/z-ai/static/logo.svg",
  },
  openGraph: {
    title: "TRION Protocol — Behavioral Truth Infrastructure",
    description:
      `C(t)=α·Φ+β·M+γ·Σ+δ·K+ε·A · T(t)=[C≥Θ]·C·e^M · BTCP Zero-Bridge across ${CHAIN_COUNT} chains`,
    siteName: "TRION",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        {children}
      </body>
    </html>
  );
}
