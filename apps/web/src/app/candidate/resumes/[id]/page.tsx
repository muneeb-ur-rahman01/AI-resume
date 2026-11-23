"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useToast } from "@/components/providers";
import { Alert, Badge, Button, Card, ErrorState, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { label } from "@/lib/format";
import type { Fact, ResumeDetail } from "@/lib/types";

function describe(f: Fact): string {
  const v = f.value as Record<string, string | boolean | null>;
  switch (f.fact_type) {
    case "skill": return String(v.name);
    case "experience": return `${v.title} at ${v.company} (${v.start ?? "?"} – ${v.is_current ? "present" : v.end ?? "?"})`;
    case "education": return [v.degree, v.field_of_study && `in ${v.field_of_study}`, v.institution && `· ${v.institution}`].filter(Boolean).join(" ");
    case "certification": return String(v.name);
    default: return String(v.text ?? "");
  }
}

const ORDER = ["headline", "summary", "skill", "experience", "education", "certification"];

export default function ResumeReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const resume = useQuery({ queryKey: ["resume", id], queryFn: () => api<ResumeDetail>(`/candidate/resumes/${id}`) });
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  const groups = useMemo(() => {
    const pending = (resume.data?.facts ?? []).filter((f) => f.status === "stated" || f.status === "inferred");
    return ORDER.map((t) => [t, pending.filter((f) => f.fact_type === t)] as const).filter(([, fs]) => fs.length);
  }, [resume.data]);

  const isChecked = (f: Fact) => selected[f.id] ?? (f.status === "stated" && (f.confidence ?? 0) >= 0.5 && f.fact_type !== "certification");

  const review = useMutation({
    mutationFn: () => {
      const pending = groups.flatMap(([, fs]) => fs);
      return api<{ applied: number; rejected: number; skipped: number }>(`/candidate/resumes/${id}/review`, {
        method: "POST",
        body: { accept: pending.filter(isChecked).map((f) => f.id), reject: pending.filter((f) => !isChecked(f)).map((f) => f.id) },
      });
    },
    onSuccess: (r) => {
      toast(`Added ${r.applied} item(s) to your profile${r.skipped ? `, skipped ${r.skipped} duplicate(s)` : ""}.`);
      qc.invalidateQueries();
      router.push("/candidate/profile");
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  if (resume.isLoading) return <LoadingBlock />;
  if (resume.isError) return <ErrorState error={resume.error} />;
  const r = resume.data!;
  const isMock = r.model_name?.startsWith("mock");

  return (
    <>
      <PageHeader title={`Review: ${r.label}`} description="Confirm what should be added to your profile. Uncheck anything that is wrong; you can edit details afterwards." />
      {isMock && <Alert tone="warning" title="Development mode">This extraction came from the deterministic mock provider, not a real AI model.</Alert>}
      {r.status_detail && <Alert tone="info" className="mt-3">{r.status_detail}</Alert>}
      {r.warnings.map((w) => <Alert key={w} tone="warning" className="mt-3">{w}</Alert>)}
      {groups.length === 0 ? (
        <Alert tone="success" className="mt-4">Everything from this resume has been reviewed.</Alert>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); review.mutate(); }} className="mt-4 space-y-4">
          {groups.map(([type, facts]) => (
            <Card key={type}>
              <fieldset>
                <legend className="font-semibold">{label(type === "skill" ? "skills" : type === "experience" ? "experience" : type)}</legend>
                <ul className="mt-3 space-y-2">
                  {facts.map((f) => (
                    <li key={f.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
                      <input id={f.id} type="checkbox" className="mt-1" checked={isChecked(f)} onChange={(e) => setSelected((s) => ({ ...s, [f.id]: e.target.checked }))} />
                      <label htmlFor={f.id} className="min-w-0 flex-1 text-sm">
                        <span className="font-medium">{describe(f)}</span>
                        <span className="ml-2 inline-flex gap-1">
                          <Badge tone={f.status === "stated" ? "info" : "warning"}>{f.status === "stated" ? "Stated in resume" : "Inferred"}</Badge>
                          {f.confidence != null && <Badge>{Math.round(f.confidence * 100)}% confidence</Badge>}
                        </span>
                        {f.source_text && <span className="mt-1 block truncate text-xs text-text-muted">Source: “{f.source_text}”</span>}
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
            </Card>
          ))}
          <p className="text-xs text-text-muted">Confidence is the extractor’s own estimate, not proof. Unchecked items are marked as rejected.</p>
          <Button type="submit" loading={review.isPending}>Add selected to my profile</Button>
        </form>
      )}
    </>
  );
}
