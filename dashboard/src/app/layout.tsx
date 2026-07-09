import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/Sidebar';
import SelfHaltBanner from '@/components/SelfHaltBanner';

export const metadata: Metadata = {
  title: 'TRION — Behavioral Truth Oracle',
  description: 'Institutional-grade multi-chain behavioral intelligence platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 flex flex-col overflow-hidden">
            <SelfHaltBanner />
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
