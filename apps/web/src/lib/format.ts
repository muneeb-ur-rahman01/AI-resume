export const label = (v: string | null | undefined) =>
  (v ?? "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export function salary(min: number | null, max: number | null, cur: string | null): string | null {
  if (min == null && max == null) return null;
  const f = (n: number) => new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
  if (min != null && max != null) return `${f(min)}–${f(max)} ${cur ?? ""}`.trim();
  return `${min != null ? "From " + f(min) : "Up to " + f(max!)} ${cur ?? ""}`.trim();
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en", { year: "numeric", month: "short", day: "numeric" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en", { dateStyle: "medium", timeStyle: "short" });
}

export function location(city: string | null, country: string | null, arrangement?: string): string {
  const place = [city, country].filter(Boolean).join(", ");
  if (arrangement === "remote") return place ? `Remote · ${place}` : "Remote";
  return [label(arrangement), place].filter(Boolean).join(" · ");
}

export const STATUS_TONE: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  submitted: "info", shortlisted: "info", interview: "warning", offer: "success", hired: "success",
  rejected: "danger", withdrawn: "neutral", draft: "neutral", published: "success", paused: "warning",
  closed: "neutral", archived: "neutral", pending_review: "warning", queued: "neutral", processing: "info",
  completed: "success", failed: "danger", verified: "success", pending: "warning", unverified: "neutral",
  suspended: "danger", eligible: "success", potentially_eligible: "info", insufficient_information: "neutral",
  ineligible: "danger",
};

export const STATUS_TEXT: Record<string, string> = {
  rejected: "Not selected", potentially_eligible: "Partial match", insufficient_information: "Not enough info",
  eligible: "Meets requirements", ineligible: "Not compatible",
};
