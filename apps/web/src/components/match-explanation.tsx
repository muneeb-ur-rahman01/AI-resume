import { CheckCircle2, HelpCircle } from "lucide-react";
import { label, STATUS_TEXT, STATUS_TONE } from "@/lib/format";
import type { Match } from "@/lib/types";
import { Badge, Card, MatchScore } from "./ui";

const COMPONENT_LABELS: Record<string, string> = {
  required_skills: "Required skills", preferred_skills: "Preferred skills", experience: "Experience", semantic: "Text similarity",
  title: "Title / job family", location: "Location & arrangement", salary: "Salary", employment_type: "Employment type",
};

export function MatchExplanation({ match }: { match: Match }) {
  const e = match.explanation;
  return (
    <Card aria-labelledby="why-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="why-title" className="font-semibold">Why this job matches</h2>
          <p className="mt-1 text-sm">{e.summary}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <MatchScore score={match.relevance_score} />
          <Badge tone={STATUS_TONE[match.eligibility]}>{STATUS_TEXT[match.eligibility] ?? label(match.eligibility)}</Badge>
        </div>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-medium">Requirements you meet</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {[...e.matched_required, ...e.matched_preferred].length === 0 && <li className="text-text-muted">None found in your confirmed profile.</li>}
            {e.matched_required.map((s) => <li key={s} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-success" aria-hidden />{s} <span className="text-xs text-text-muted">(required)</span></li>)}
            {e.matched_preferred.map((s) => <li key={s} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-success" aria-hidden />{s} <span className="text-xs text-text-muted">(preferred)</span></li>)}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-medium">Not in your confirmed profile</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {[...e.missing_required, ...e.missing_preferred].length === 0 && <li className="text-text-muted">Nothing missing.</li>}
            {e.missing_required.map((s) => <li key={s} className="flex items-center gap-2"><HelpCircle className="h-4 w-4 text-warning" aria-hidden />{s} <span className="text-xs text-text-muted">(required)</span></li>)}
            {e.missing_preferred.map((s) => <li key={s} className="flex items-center gap-2"><HelpCircle className="h-4 w-4 text-text-muted" aria-hidden />{s} <span className="text-xs text-text-muted">(preferred)</span></li>)}
          </ul>
        </div>
      </div>
      <p className="mt-4 text-sm"><span className="font-medium">Experience: </span>{e.experience}</p>
      {e.preferences.map((p) => <p key={p} className="mt-1 text-sm text-warning">{p}</p>)}
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium text-primary">How the score is calculated</summary>
        <table className="mt-3 w-full text-left text-sm">
          <caption className="sr-only">Score components</caption>
          <thead><tr className="border-b border-border text-text-muted"><th className="py-1 font-medium">Factor</th><th className="font-medium">Weight</th><th className="font-medium">Score</th><th className="font-medium">Detail</th></tr></thead>
          <tbody>
            {Object.entries(match.components).map(([k, c]) => (
              <tr key={k} className="border-b border-border/60">
                <td className="py-1.5">{COMPONENT_LABELS[k] ?? k}</td>
                <td>{Math.round(c.weight * 100)}%</td>
                <td>{c.score == null ? <span className="text-text-muted">n/a</span> : `${Math.round(c.score * 100)}%`}</td>
                <td className="text-text-muted">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-text-muted">Factors marked n/a lack data and are excluded; weights are re-normalized. Data coverage: {Math.round(e.data_coverage * 100)}%. {e.disclaimer}</p>
      </details>
    </Card>
  );
}
