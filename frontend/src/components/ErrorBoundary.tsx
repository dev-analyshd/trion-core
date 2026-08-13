'use client';

/**
 * TRION Error Boundary — catches render errors, shows fallback UI.
 *
 * Phase 8.1: Wrap the main app in <ErrorBoundary> so a single component
 * crashing doesn't take down the entire dashboard. Logs structured error
 * context to console for debugging.
 */
import React, { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Structured logging — Phase 8.1
    console.error('[TRION ErrorBoundary]', {
      timestamp: new Date().toISOString(),
      error: {
        name: error.name,
        message: error.message,
        stack: error.stack,
      },
      componentStack: errorInfo.componentStack,
      url: typeof window !== 'undefined' ? window.location.href : '',
    });
    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center">
          <div className="max-w-md">
            <div className="text-6xl mb-4 opacity-30" aria-hidden>⚠</div>
            <h1 className="text-2xl font-bold mb-2">Something went wrong</h1>
            <p className="text-sm text-muted-foreground mb-6">
              An unexpected error occurred while rendering this page. The error
              has been logged. Try reloading — if the problem persists, clear
              your browser cache.
            </p>
            {this.state.error && (
              <details className="mb-6 text-left">
                <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                  Error details
                </summary>
                <pre className="mt-2 p-3 rounded-lg bg-muted text-xs font-mono overflow-auto max-h-40">
                  {this.state.error.name}: {this.state.error.message}
                  {this.state.error.stack && '\n\n' + this.state.error.stack}
                </pre>
              </details>
            )}
            <div className="flex gap-3 justify-center">
              <button
                onClick={this.handleReset}
                className="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              >
                Try again
              </button>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity"
              >
                Reload page
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
