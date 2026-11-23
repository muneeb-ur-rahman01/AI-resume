"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useToast } from "@/components/providers";
import { Timeline } from "@/components/timeline";
import { Badge, Button, Card, ConfirmDialog, ErrorState, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dateTime, label, STATUS_TEXT, STATUS_TONE } from "@/lib/format";
import type { Application } from "@/lib/types";

const WITHDRAWABLE = new Set(["submitted", "shortlisted", "interview", "offer"]);

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const app = useQuery({ queryKey: ["application", id], queryFn: () => api<Application>(`/candidate/applications/${id}`) });
  const withdraw = useMutation({
    mutationFn: () => api<Application>(`/candidate/applications/${id}/withdraw`, { method: "POST" }),
    onSuccess: (a) => { qc.setQueryData(["application", id], a); qc.invalidateQueries({ queryKey: ["applications"] }); setConfirm(false); toast("Application withdrawn."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  if (app.isLoading) return <LoadingBlock />;
  if (app.isError) return <ErrorState error={app.error} />;
  const a = app.data!;
  const letter = a.documents.find((d) => d.kind === "cover_letter");
  return (
    <>
      <PageHeader title={a.job.title} description={`${a.job.company.name} · submitted ${dateTime(a.submitted_at)}`}
        actions={<><Badge tone={STATUS_TONE[a.status]}>{STATUS_TEXT[a.status] ?? label(a.status)}</Badge>{WITHDRAWABLE.has(a.status) && <Button variant="secondary" onClick={() => setConfirm(true)}>Withdraw</Button>}</>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <h2 className="mb-4 font-semibold">Timeline</h2>
          <Timeline items={a.history} />
          <p className="text-xs text-text-muted">“Submitted” means your application was delivered to the employer’s CareerPilot inbox. Other statuses appear only when the employer records them.</p>
        </Card>
        <div className="space-y-6 lg:col-span-2">
          {a.interviews.length > 0 && (
            <Card>
              <h2 className="font-semibold">Interviews</h2>
              <ul className="mt-2 space-y-2 text-sm">{a.interviews.map((i) => <li key={i.id}>{dateTime(i.starts_at)} · {i.duration_minutes} min {i.location_or_link && `· ${i.location_or_link}`}</li>)}</ul>
            </Card>
          )}
          <Card>
            <h2 className="font-semibold">Submitted materials</h2>
            <p className="mt-2 text-sm">Resume: {a.resume_label ?? "none attached"}</p>
            {letter ? <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-surface-muted p-4 font-sans text-sm">{letter.content}</pre> : <p className="mt-2 text-sm text-text-muted">No cover letter.</p>}
          </Card>
          <p className="text-sm"><Link href={`/jobs/${a.job.id}`} className="text-primary underline">View job posting</Link></p>
        </div>
      </div>
      <ConfirmDialog open={confirm} title="Withdraw this application?" tone="danger" confirmLabel="Withdraw" loading={withdraw.isPending}
        description="The employer will see that you withdrew. You can't re-apply to the same job." onClose={() => setConfirm(false)} onConfirm={() => withdraw.mutate()} />
    </>
  );
}
