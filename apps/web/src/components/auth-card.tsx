import Link from "next/link";
import type { ReactNode } from "react";

export function AuthCard({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <Link href="/" className="mb-6 text-lg font-semibold tracking-tight">CareerPilot<span className="text-primary"> AI</span></Link>
      <main className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h1 className="text-xl font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-text-muted">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </main>
      {footer && <div className="mt-4 text-sm text-text-muted">{footer}</div>}
    </div>
  );
}
