"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useToast } from "@/components/providers";
import { Timeline } from "@/components/timeline";
import { Alert, Badge, Button, Card, ConfirmDialog, ErrorState, Field, Input, LoadingBlock, PageHeader, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dateTime, label, STATUS_TEXT, STATUS_TONE } from "@/lib/format";
import type { EmployerAppDetail } from "@/lib/types";

const ACTION_LABEL: Record<string, string> = { shortlisted: "Shortlist", interview: "Move to interview", offer: "Make offer", rejected: "Reject", hired: "Mark hired" };

export default function EmployerApplicationPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const toast = useToast();
  const [pending, setPending] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [interview, setInterview] = useState({ starts_at: "", duration_minutes: 45, location_or_link: "" });
  const app = useQuery({ queryKey: ["employer-app", id], queryFn: () => api<EmployerAppDetail>(`/employer/applications/${id}`) });
  const update = useMutation({
    mutationFn: (status: string) => api<EmployerAppDetail>(`/employer/applications/${id}/status`, { method: "POST", body: { status, note: note || null } }),
    onSuccess: (d) => { qc.setQueryData(["employer-app", id], d); qc.invalidateQueries({ queryKey: ["job-apps"] }); setPending(null); setNote(""); toast("Status updated. The candidate was notified."); },
    onError: (e) => { setPending(null); toast(errorMessage(e), "danger"); },
  });
  const schedule = useMutation({
    mutationFn: () => api(`/employer/applications/${id}/interviews`, { method: "POST", body: { ...interview, starts_at: new Date(interview.starts_at).toISOString(), location_or_link: interview.location_or_link || null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["employer-app", id] }); toast("Interview scheduled."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  if (app.isLoading) return <LoadingBlock />;
  if (app.isError) return <ErrorState error={app.error} />;
  const a = app.data!;
  const c = a.candidate as { name?: string; email?: string; headline?: string; summary?: string; skills?: string[]; years_experience?: number; experiences?: { title: string; company: string; start?: string; end?: string; is_current?: boolean }[]; educations?: { institution: string; degree?: string }[] };
  const letter = a.documents.find((d) => d.kind === "cover_letter");
  return (
    <>
      <p className="mb-4 text-sm"><Link href={`/employer/jobs/${a.job.id}`} className="text-primary underline">← {a.job.title}</Link></p>
      <PageHeader title={a.candidate_name} description={a.candidate_headline ?? undefined}
        actions={<><Badge tone={STATUS_TONE[a.status]}>{STATUS_TEXT[a.status] ?? label(a.status)}</Badge>{a.allowed_transitions.map((t) => <Button key={t} variant={t === "rejected" ? "danger" : "secondary"} onClick={() => setPending(t)}>{ACTION_LABEL[t] ?? label(t)}</Button>)}</>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <h2 className="font-semibold">Candidate profile (as submitted)</h2>
            <p className="mt-2 text-sm">Contact: {c.email ?? "—"}</p>
            {c.summary && <p className="mt-2 text-sm">{c.summary}</p>}
            <p className="mt-3 text-sm"><span className="font-medium">Skills:</span> {c.skills?.join(", ") || "—"}</p>
            <p className="mt-1 text-sm"><span className="font-medium">Experience:</span> {c.years_experience != null ? `${c.years_experience} years` : "—"}</p>
            <ul className="mt-3 space-y-1 text-sm">{c.experiences?.map((e, i) => <li key={i}>{e.title} · {e.company} ({e.start ?? "?"} – {e.is_current ? "present" : e.end ?? "?"})</li>)}</ul>
            <ul className="mt-3 space-y-1 text-sm">{c.educations?.map((e, i) => <li key={i}>{e.degree ?? "Studies"} · {e.institution}</li>)}</ul>
            {a.has_resume && <a className="mt-4 inline-block text-sm text-primary underline" href={`/api/v1/employer/applications/${a.id}/resume`}>Download resume</a>}
          </Card>
          <Card>
            <h2 className="font-semibold">Cover letter</h2>
            {letter ? <pre className="mt-3 whitespace-pre-wrap font-sans text-sm">{letter.content}</pre> : <p className="mt-2 text-sm text-text-muted">No cover letter.</p>}
          </Card>
          {a.relevance && (
            <Card>
              <h2 className="font-semibold">Relevance summary (advisory)</h2>
              <p className="mt-2 text-sm">{a.relevance.explanation.summary} Score {a.relevance.score}/100.</p>
              {a.relevance.explanation.missing_required.length > 0 && <p className="mt-1 text-sm text-text-muted">Not found in the candidate’s confirmed profile: {a.relevance.explanation.missing_required.join(", ")}</p>}
              <Alert tone="neutral" className="mt-3">This is a heuristic signal computed from the candidate’s confirmed profile. It is not a prediction of job performance and must not be the sole basis for a decision.</Alert>
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card><h2 className="mb-4 font-semibold">Timeline</h2><Timeline items={a.history} showNotes /></Card>
          {["submitted", "shortlisted", "interview"].includes(a.status) && (
            <Card>
              <h2 className="font-semibold">Schedule interview</h2>
              <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); schedule.mutate(); }}>
                <Field label="Date and time" required>{(p) => <Input {...p} type="datetime-local" required value={interview.starts_at} onChange={(e) => setInterview({ ...interview, starts_at: e.target.value })} />}</Field>
                <Field label="Duration (minutes)">{(p) => <Input {...p} type="number" min={15} max={480} value={interview.duration_minutes} onChange={(e) => setInterview({ ...interview, duration_minutes: Number(e.target.value) })} />}</Field>
                <Field label="Location or meeting link">{(p) => <Input {...p} value={interview.location_or_link} onChange={(e) => setInterview({ ...interview, location_or_link: e.target.value })} />}</Field>
                <Button type="submit" loading={schedule.isPending}>Schedule</Button>
              </form>
              {a.interviews.map((i) => <p key={i.id} className="mt-2 text-sm">{dateTime(i.starts_at)} · {i.duration_minutes} min</p>)}
            </Card>
          )}
        </div>
      </div>
      <ConfirmDialog open={!!pending} title={`${ACTION_LABEL[pending ?? ""] ?? "Update"} this candidate?`} tone={pending === "rejected" ? "danger" : "primary"}
        description="The candidate will be notified of the new status. Notes are visible to your team only." loading={update.isPending}
        onClose={() => setPending(null)} onConfirm={() => pending && update.mutate(pending)}>
        <Field label="Internal note (optional)">{(p) => <Textarea {...p} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
      </ConfirmDialog>
    </>
  );
}
