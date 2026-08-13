import type { Metadata } from 'next';
import './globals.css';
import Web3Provider from '../providers/Web3Provider';

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
      <body>
        <Web3Provider>{children}</Web3Provider>
      </body>
    </html>
  );
}
