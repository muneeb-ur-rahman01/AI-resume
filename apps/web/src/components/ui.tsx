"use client";

import { clsx } from "clsx";
import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { forwardRef, useEffect, useId, useRef, type ComponentProps, type ReactNode } from "react";
import { twMerge } from "tailwind-merge";

export const cn = (...inputs: Parameters<typeof clsx>) => twMerge(clsx(inputs));

// ------------------------------------------------------------------------------------------- Button
type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-primary-hover",
  secondary: "bg-surface text-text border border-border-strong hover:bg-surface-muted",
  ghost: "text-text hover:bg-surface-muted",
  danger: "bg-danger text-white hover:opacity-90",
};

type ButtonProps = ComponentProps<"button"> & { variant?: Variant; loading?: boolean; size?: "sm" | "md" };
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", loading, size = "md", className, children, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        size === "sm" ? "h-8 px-3 text-sm" : "h-10 px-4 text-sm",
        variants[variant],
        className,
      )}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

export function LinkButton({ href, variant = "primary", className, children }: { href: string; variant?: Variant; className?: string; children: ReactNode }) {
  return (
    <Link href={href} className={cn("inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium", variants[variant], className)}>
      {children}
    </Link>
  );
}

// ------------------------------------------------------------------------------------------- Fields
const inputBase =
  "w-full rounded-lg border border-border-strong bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted/70 aria-[invalid=true]:border-danger";

export const Input = forwardRef<HTMLInputElement, ComponentProps<"input">>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={cn(inputBase, "h-10", className)} {...p} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, ComponentProps<"textarea">>(function Textarea({ className, ...p }, ref) {
  return <textarea ref={ref} className={cn(inputBase, "min-h-24", className)} {...p} />;
});

export const Select = forwardRef<HTMLSelectElement, ComponentProps<"select">>(function Select({ className, ...p }, ref) {
  return <select ref={ref} className={cn(inputBase, "h-10", className)} {...p} />;
});

/** Label + control + hint + error, wired with aria-describedby / aria-invalid. */
export function Field({ label, hint, error, children, required }: {
  label: string; hint?: string; error?: string; required?: boolean;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}) {
  const id = useId();
  const describedBy = [hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium">
        {label} {required && <span aria-hidden className="text-danger">*</span>}
      </label>
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {hint && <p id={`${id}-hint`} className="text-xs text-text-muted">{hint}</p>}
      {error && <p id={`${id}-err`} role="alert" className="text-xs text-danger">{error}</p>}
    </div>
  );
}

// -------------------------------------------------------------------------------------- Containers
export function Card({ className, children, ...p }: ComponentProps<"section">) {
  return <section className={cn("rounded-[var(--radius-card)] border border-border bg-surface p-5 shadow-sm", className)} {...p}>{children}</section>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ Status
type Tone = "neutral" | "info" | "success" | "warning" | "danger";
const tones: Record<Tone, string> = {
  neutral: "bg-surface-muted text-text-muted border-border",
  info: "bg-info-soft text-info border-info/20",
  success: "bg-success-soft text-success border-success/20",
  warning: "bg-warning-soft text-warning border-warning/20",
  danger: "bg-danger-soft text-danger border-danger/20",
};

/** Badges always carry text, so status is never conveyed by color alone. */
export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone], className)}>{children}</span>;
}

const alertIcon = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: XCircle, neutral: Info };
export function Alert({ tone = "info", title, children, className }: { tone?: Tone; title?: string; children?: ReactNode; className?: string }) {
  const Icon = alertIcon[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-lg border p-3 text-sm", tones[tone], className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && "mt-0.5", "text-text")}>{children}</div>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-surface-muted", className)} />;
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}…</span>
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-[var(--radius-card)] border border-dashed border-border-strong bg-surface px-6 py-12 text-center">
      {icon && <div className="mb-3 text-text-muted" aria-hidden>{icon}</div>}
      <h2 className="text-base font-semibold">{title}</h2>
      {description && <p className="mt-1 max-w-md text-sm text-text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const status = (error as { status?: number })?.status;
  const message = (error as Error)?.message ?? "Something went wrong.";
  if (status === 403) return <Alert tone="warning" title="You don't have access to this page">{message}</Alert>;
  if (status === 404) return <Alert tone="neutral" title="Not found">{message}</Alert>;
  return (
    <Alert tone="danger" title="We couldn't load this">
      <p>{message}</p>
      {onRetry && <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>Try again</Button>}
    </Alert>
  );
}

// ----------------------------------------------------------------------------------------- Dialog
/** Accessible modal built on <dialog>: focus is trapped by the browser, Esc closes it. */
export function ConfirmDialog({ open, title, description, confirmLabel = "Confirm", tone = "primary", loading, onConfirm, onClose, children }: {
  open: boolean; title: string; description?: string; confirmLabel?: string; tone?: "primary" | "danger";
  loading?: boolean; onConfirm: () => void; onClose: () => void; children?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="dlg-title" className="w-[min(32rem,92vw)] rounded-xl border border-border p-0 backdrop:bg-black/40">
      <div className="p-5">
        <h2 id="dlg-title" className="text-lg font-semibold">{title}</h2>
        {description && <p className="mt-2 text-sm text-text-muted">{description}</p>}
        {children && <div className="mt-4">{children}</div>}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant={tone} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </dialog>
  );
}

// ----------------------------------------------------------------------------------- Match score
/** Relevance meter with a numeric label (not color-only) and an explicit "not a hiring probability" note. */
export function MatchScore({ score, eligibility }: { score: number; eligibility?: string }) {
  const tone = score >= 75 ? "bg-success" : score >= 50 ? "bg-primary" : "bg-warning";
  return (
    <div className="min-w-32">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-text-muted">Relevance</span>
        <span className="text-sm font-semibold" aria-label={`Relevance score ${score} out of 100`}>{score}/100</span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-surface-muted" aria-hidden>
        <div className={cn("h-2 rounded-full", tone)} style={{ width: `${Math.max(3, score)}%` }} />
      </div>
      {eligibility && <p className="mt-1 text-xs text-text-muted">{eligibility}</p>}
    </div>
  );
}
