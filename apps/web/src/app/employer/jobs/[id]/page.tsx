"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { jobToValues, JobForm } from "@/components/job-form";
import { useToast } from "@/components/providers";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { date, label, STATUS_TEXT, STATUS_TONE } from "@/lib/format";
import type { EmployerAppRow, Job, Page } from "@/lib/types";

const ACTIONS: Record<string, { to: string; label: string; variant?: "primary" | "secondary" | "danger" }[]> = {
  draft: [{ to: "published", label: "Publish" }],
  published: [{ to: "paused", label: "Pause", variant: "secondary" }, { to: "closed", label: "Close", variant: "danger" }],
  paused: [{ to: "published", label: "Republish" }, { to: "closed", label: "Close", variant: "danger" }],
  closed: [{ to: "archived", label: "Archive", variant: "secondary" }],
};

export default function EmployerJobPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const job = useQuery({ queryKey: ["employer-job", id], queryFn: () => api<Job>(`/employer/jobs/${id}`) });
  const apps = useQuery({ queryKey: ["job-apps", id], queryFn: () => api<Page<EmployerAppRow>>(`/employer/jobs/${id}/applications?page_size=100`) });
  const transition = useMutation({
    mutationFn: (status: string) => api<Job>(`/employer/jobs/${id}/status`, { method: "POST", body: { status } }),
    onSuccess: (j) => { qc.setQueryData(["employer-job", id], j); qc.invalidateQueries({ queryKey: ["company-jobs"] }); toast(`Job is now ${label(j.status)}.`); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  if (job.isLoading) return <LoadingBlock />;
  if (job.isError) return <ErrorState error={job.error} />;
  const j = job.data!;
  const editable = ["draft", "paused", "pending_review"].includes(j.status);
  return (
    <>
      <PageHeader title={j.title} description={`Created ${date(j.created_at)}${j.published_at ? ` · published ${date(j.published_at)}` : ""}`}
        actions={<>
          <Badge tone={STATUS_TONE[j.status]}>{label(j.status)}</Badge>
          {(ACTIONS[j.status] ?? []).map((a) => <Button key={a.to} variant={a.variant ?? "primary"} loading={transition.isPending && transition.variables === a.to} onClick={() => transition.mutate(a.to)}>{a.label}</Button>)}
          {editable && <Button variant="secondary" onClick={() => setEditing((e) => !e)}>{editing ? "Cancel edit" : "Edit"}</Button>}
          {j.status === "published" && <Link className="self-center text-sm text-primary underline" href={`/jobs/${j.id}`}>Public preview</Link>}
        </>} />
      {j.status === "published" && <Alert tone="info" className="mb-4">Pause the job to edit it.</Alert>}
      {editing ? (
        <JobForm initial={jobToValues(j)} submitLabel="Save changes" error={editError} onSubmit={async (payload) => {
          setEditError(null);
          try {
            const updated = await api<Job>(`/employer/jobs/${id}`, { method: "PUT", body: { ...payload, expected_version: j.version } });
            qc.setQueryData(["employer-job", id], updated); setEditing(false); toast("Job updated.");
          } catch (e) { setEditError(errorMessage(e)); }
        }} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-1">
            <h2 className="font-semibold">Requirements</h2>
            <ul className="mt-2 flex flex-wrap gap-2">{j.skills.map((s) => <li key={s.name}><Badge tone={s.requirement === "required" ? "info" : "neutral"}>{s.name} · {s.requirement}</Badge></li>)}</ul>
            <p className="mt-3 text-sm">{label(j.employment_type)} · {label(j.work_arrangement)}{j.location_country ? ` · ${j.location_country}` : ""}</p>
            <p className="mt-3 whitespace-pre-line text-sm text-text-muted">{j.description}</p>
          </Card>
          <Card className="overflow-x-auto p-0 lg:col-span-2">
            <h2 className="p-4 font-semibold">Applicants ({apps.data?.total ?? 0})</h2>
            {apps.isLoading && <div className="p-4"><LoadingBlock /></div>}
            {apps.data?.items.length === 0 && <div className="p-4"><EmptyState title="No applicants yet" /></div>}
            {apps.data && apps.data.items.length > 0 && (
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Applicants</caption>
                <thead className="border-y border-border bg-surface-muted text-text-muted"><tr><th className="px-4 py-2 font-medium">Candidate</th><th className="px-4 py-2 font-medium">Relevance (advisory)</th><th className="px-4 py-2 font-medium">Status</th><th className="px-4 py-2 font-medium">Applied</th></tr></thead>
                <tbody>
                  {apps.data.items.map((a) => (
                    <tr key={a.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3"><Link href={`/employer/applications/${a.id}`} className="font-medium hover:underline">{a.candidate_name}</Link>{a.candidate_headline && <p className="text-xs text-text-muted">{a.candidate_headline}</p>}{!a.first_viewed_at && <Badge tone="info" className="mt-1">New</Badge>}</td>
                      <td className="px-4 py-3">{a.relevance_score != null ? `${a.relevance_score}/100` : "—"}</td>
                      <td className="px-4 py-3"><Badge tone={STATUS_TONE[a.status]}>{STATUS_TEXT[a.status] ?? label(a.status)}</Badge></td>
                      <td className="px-4 py-3">{date(a.submitted_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
