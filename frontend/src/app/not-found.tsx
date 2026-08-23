'use client';

/**
 * TRION 404 page - not found.
 * Phase 8.1: Friendly error page with link back to dashboard.
 */
import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center">
      <div className="max-w-md">
        <div className="text-8xl font-bold text-muted-foreground/30 mb-4" aria-hidden>
          404
        </div>
        <h1 className="text-2xl font-bold mb-2">Page not found</h1>
        <p className="text-sm text-muted-foreground mb-6">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/"
          className="inline-block px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity"
        >
          &lt;- Back to dashboard
        </Link>
      </div>
    </div>
  );
}
