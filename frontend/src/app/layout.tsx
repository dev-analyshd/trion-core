import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import Web3Provider from '../providers/Web3Provider';
import { ErrorBoundary } from '../components/ErrorBoundary';

// Phase 4.1: Inter for body, JetBrains Mono for code/addresses
const inter = Inter({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

// Phase 4.3: Comprehensive metadata
export const metadata: Metadata = {
  metadataBase: new URL('https://trion.io'),
  title: {
    default: 'TRION Protocol - Behavioral Truth Oracle',
    template: '%s - TRION Protocol',
  },
  description:
    'Multi-chain behavioral truth oracle with cryptographic coherence scoring across 128 chains and 18 VM families. BTCP cross-chain routing + Continuum clearing network.',
  applicationName: 'TRION Protocol',
  authors: [{ name: 'TRION Protocol' }],
  generator: 'Next.js',
  keywords: [
    'TRION', 'behavioral truth oracle', 'cross-chain', 'BTCP',
    'Continuum', 'BEO', 'Akashic Index', 'DW-BFT', 'FAISS',
    'multi-chain', 'DeFi', 'oracle',
  ],
  referrer: 'origin-when-cross-origin',
  icons: {
    icon: '/trion_logo.png',
    shortcut: '/trion_logo.png',
    apple: '/trion_logo.png',
  },
  openGraph: {
    title: 'TRION Protocol - The Behavioral Truth Oracle',
    description:
      'The first substrate-independent behavioral truth infrastructure. 128 chains, 18 VM families, BTCP + Continuum clearing.',
    type: 'website',
    siteName: 'TRION Protocol',
    images: ['/trion_logo.png'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'TRION Protocol',
    description: 'Behavioral truth oracle across 128 chains.',
    images: ['/trion_logo.png'],
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)',  color: '#0a0a0f' },
  ],
};

// JSON-LD structured data
const jsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'TRION Protocol',
  applicationCategory: 'FinancialApplication',
  operatingSystem: 'Web',
  description:
    'Multi-chain behavioral truth oracle with cryptographic coherence scoring across 128 chains.',
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Apply theme before paint to avoid FOUC */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('trion-theme')||'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`,
          }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className="bg-background text-foreground antialiased">
        <ErrorBoundary>
          <Web3Provider>{children}</Web3Provider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
