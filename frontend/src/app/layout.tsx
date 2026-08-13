import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'TRION Protocol — Behavioral Truth Oracle',
  description: 'Multi-chain behavioral truth oracle with cryptographic coherence scoring across 100+ chains and 14 VM families',
  icons: {
    icon: '/trion_logo.png',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
