'use client';

/**
 * TRION 500 page — server error.
 * Phase 8.1: Friendly error page shown on unhandled server errors.
 */
import Link from 'next/link';

export default function ServerError() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center">
      <div className="max-w-md">
        <div className="text-8xl font-bold text-red-500/30 mb-4" aria-hidden>
          500
        </div>
        <h1 className="text-2xl font-bold mb-2">Server error</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Something went wrong on our end. The error has been logged. Please try
          again in a moment.
        </p>
        <Link
          href="/"
          className="inline-block px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity"
        >
          ← Back to dashboard
        </Link>
      </div>
    </div>
  );
}
