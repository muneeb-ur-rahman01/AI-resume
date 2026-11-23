"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Building2, ExternalLink, Flag, MapPin, Wallet } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { MatchExplanation } from "@/components/match-explanation";
import { useToast } from "@/components/providers";
import { Badge, Button, Card, ConfirmDialog, ErrorState, Field, LinkButton, LoadingBlock, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { date, label, location, salary } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import type { Job, Match } from "@/lib/types";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const toast = useToast();
  const isCandidate = !!me.data?.roles.includes("candidate");
  const job = useQuery({ queryKey: ["job", id], queryFn: () => api<Job>(`/jobs/${id}`) });
  const match = useQuery({ queryKey: ["match", id], queryFn: () => api<Match>(`/candidate/jobs/${id}/match`), enabled: isCandidate });
  const save = useMutation({ mutationFn: () => api(`/candidate/saved-jobs/${id}`, { method: "PUT" }), onSuccess: () => toast("Job saved.") });
  const [reportOpen, setReportOpen] = useState(false);
  const [report, setReport] = useState({ reason: "fraud", details: "" });
  const sendReport = useMutation({
    mutationFn: () => api(`/jobs/${id}/reports`, { method: "POST", body: { reason: report.reason, details: report.details || null } }),
    onSuccess: () => { setReportOpen(false); toast("Report sent to moderators."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <p className="mb-6 text-sm"><Link href={isCandidate ? "/candidate/recommendations" : "/jobs"} className="text-primary underline">← Back</Link></p>
      {job.isLoading && <LoadingBlock />}
      {job.isError && <ErrorState error={job.error} />}
      {job.data && (
        <div className="space-y-6">
          <Card>
            <h1 className="text-2xl font-semibold">{job.data.title}</h1>
            <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-text-muted">
              <span className="inline-flex items-center gap-1"><Building2 className="h-4 w-4" aria-hidden />{job.data.company.name}</span>
              {job.data.company.verification_status === "verified" ? <Badge tone="success">Verified employer</Badge> : <Badge>Unverified employer</Badge>}
              <span className="inline-flex items-center gap-1"><MapPin className="h-4 w-4" aria-hidden />{location(job.data.location_city, job.data.location_country, job.data.work_arrangement)}</span>
              {salary(job.data.salary_min, job.data.salary_max, job.data.salary_currency) && <span className="inline-flex items-center gap-1"><Wallet className="h-4 w-4" aria-hidden />{salary(job.data.salary_min, job.data.salary_max, job.data.salary_currency)}</span>}
              <span>{label(job.data.employment_type)}</span>
              {job.data.application_deadline && <span>Apply by {date(job.data.application_deadline)}</span>}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {isCandidate && (job.data.external_apply_url ? (
                <a href={job.data.external_apply_url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white">Apply on employer site <ExternalLink className="h-4 w-4" aria-hidden /></a>
              ) : <LinkButton href={`/candidate/apply/${id}`}>Prepare application</LinkButton>)}
              {isCandidate && <Button variant="secondary" onClick={() => save.mutate()} loading={save.isPending}>Save job</Button>}
              {!me.data && <LinkButton href={`/login?next=/jobs/${id}`}>Sign in to apply</LinkButton>}
              {me.data && <Button variant="ghost" onClick={() => setReportOpen(true)}><Flag className="h-4 w-4" aria-hidden />Report</Button>}
            </div>
            {job.data.external_apply_url && isCandidate && <p className="mt-2 text-xs text-text-muted">This employer accepts applications on their own site. CareerPilot does not submit to external sites.</p>}
          </Card>
          {isCandidate && match.data && <MatchExplanation match={match.data} />}
          {isCandidate && match.isError && <ErrorState error={match.error} />}
          <Card>
            <h2 className="font-semibold">About the role</h2>
            <p className="mt-3 whitespace-pre-line text-sm leading-6">{job.data.description}</p>
            {job.data.responsibilities.length > 0 && (<><h3 className="mt-5 font-medium">Responsibilities</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{job.data.responsibilities.map((r) => <li key={r}>{r}</li>)}</ul></>)}
            <h3 className="mt-5 font-medium">Skills</h3>
            <ul className="mt-2 flex flex-wrap gap-2">
              {job.data.skills.map((s) => <li key={s.name}><Badge tone={s.requirement === "required" ? "info" : "neutral"}>{s.name} · {s.requirement}</Badge></li>)}
            </ul>
            {job.data.min_experience_years != null && <p className="mt-4 text-sm">Experience: {job.data.min_experience_years}{job.data.max_experience_years != null ? `–${job.data.max_experience_years}` : "+"} years</p>}
            {job.data.benefits.length > 0 && (<><h3 className="mt-5 font-medium">Benefits</h3><ul className="mt-2 list-disc pl-5 text-sm">{job.data.benefits.map((b) => <li key={b}>{b}</li>)}</ul></>)}
          </Card>
        </div>
      )}
      <ConfirmDialog open={reportOpen} title="Report this job" confirmLabel="Send report" loading={sendReport.isPending} onClose={() => setReportOpen(false)} onConfirm={() => sendReport.mutate()}
        description="Reports are reviewed by moderators. Use this for fraudulent, discriminatory, misleading or abusive postings.">
        <div className="space-y-3">
          <Field label="Reason">{(a) => <Select {...a} value={report.reason} onChange={(e) => setReport({ ...report, reason: e.target.value })}><option value="fraud">Fraud or scam</option><option value="discriminatory">Discriminatory</option><option value="misleading">Misleading</option><option value="abusive">Abusive</option><option value="other">Other</option></Select>}</Field>
          <Field label="Details (optional)">{(a) => <Textarea {...a} maxLength={2000} value={report.details} onChange={(e) => setReport({ ...report, details: e.target.value })} />}</Field>
        </div>
      </ConfirmDialog>
    </div>
  );
}
