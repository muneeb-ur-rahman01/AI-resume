"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useToast } from "@/components/providers";
import { Alert, Badge, Button, Card, ConfirmDialog, ErrorState, Field, LoadingBlock, PageHeader, Select, Textarea } from "@/components/ui";
import { api, ApiError, errorMessage, newIdempotencyKey } from "@/lib/api";
import type { Application, CoverLetter, Preview } from "@/lib/types";

export default function ApplyPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const preview = useQuery({ queryKey: ["preview", jobId], queryFn: () => api<Preview>(`/candidate/applications/preview?job_id=${jobId}`) });
  // Edited values override what the server returned; until edited, show the saved draft / primary resume.
  const [letterEdit, setLetter] = useState<string | null>(null);
  const [draftState, setDraft] = useState<CoverLetter | null>(null);
  const [resumeChoice, setResumeId] = useState<string | null>(null);
  const draft = draftState ?? preview.data?.cover_letter_draft ?? null;
  const letter = letterEdit ?? draft?.content ?? "";
  const resumeId = resumeChoice ?? preview.data?.resumes[0]?.id ?? "";
  const [tone, setTone] = useState("professional");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [approved, setApproved] = useState(false);
  const idempotencyKey = useRef(newIdempotencyKey()); // stable across retries of this submission

  const generate = useMutation({
    mutationFn: () => api<CoverLetter>(`/candidate/jobs/${jobId}/cover-letters/generate`, { method: "POST", body: { tone } }),
    onSuccess: (d) => { setDraft(d); setLetter(d.content); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const saveDraft = useMutation({
    mutationFn: () => api<CoverLetter>(`/candidate/jobs/${jobId}/cover-letters`, { method: "POST", body: { content: letter } }),
    onSuccess: (d) => { setDraft(d); toast(`Saved as version ${d.version_number}.`); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const submit = useMutation({
    mutationFn: async () => {
      let current = draft;
      if (letter.trim() && (!draft || draft.content !== letter)) current = await api<CoverLetter>(`/candidate/jobs/${jobId}/cover-letters`, { method: "POST", body: { content: letter } });
      return api<Application>("/candidate/applications", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey.current },
        body: { job_id: jobId, resume_id: resumeId || null, cover_letter_draft_id: letter.trim() ? current?.id ?? null : null, confirm: true },
      });
    },
    onSuccess: (app) => { qc.invalidateQueries({ queryKey: ["applications"] }); toast("Application submitted."); router.push(`/candidate/applications/${app.id}`); },
    onError: (e) => { setConfirmOpen(false); toast(errorMessage(e), "danger"); if (e instanceof ApiError && e.code === "duplicate_application") preview.refetch(); },
  });

  if (preview.isLoading) return <LoadingBlock />;
  if (preview.isError) return <ErrorState error={preview.error} />;
  const p = preview.data!;
  if (p.already_applied) return <Alert tone="info" title="You already applied to this job">See <Link className="underline" href="/candidate/applications">your applications</Link>.</Alert>;
  if (p.external_apply_url) return <Alert tone="info" title="External application">This employer accepts applications on <a className="underline" href={p.external_apply_url} rel="noopener noreferrer nofollow" target="_blank">their own site</a>.</Alert>;
  const claims = draft && draft.content === letter ? draft.unsupported_claims : null;
  const isMock = draft?.generated_by?.startsWith("mock");

  return (
    <>
      <PageHeader title={`Apply: ${p.job.title}`} description={`${p.job.company.name} · Review everything below. Nothing is sent until you confirm.`} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <h2 className="font-semibold">Cover letter (optional)</h2>
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <Field label="Tone">{(a) => <Select {...a} value={tone} onChange={(e) => setTone(e.target.value)}><option value="professional">Professional</option><option value="warm">Warm</option><option value="concise">Concise</option></Select>}</Field>
              <Button variant="secondary" onClick={() => generate.mutate()} loading={generate.isPending}><Sparkles className="h-4 w-4" aria-hidden />{draft ? "Regenerate" : "Draft with AI"}</Button>
            </div>
            {isMock && <Alert tone="warning" className="mt-3">Drafted by the deterministic development mock, not a real AI model.</Alert>}
            <div className="mt-3">
              <Field label="Letter" hint="Drafted only from your confirmed profile. Edit freely; you are responsible for its accuracy.">
                {(a) => <Textarea {...a} className="min-h-72" maxLength={6000} value={letter} onChange={(e) => setLetter(e.target.value)} />}
              </Field>
            </div>
            {claims && claims.length > 0 && (
              <Alert tone="warning" title="Check these statements" className="mt-3">
                <ul className="list-disc pl-5">{claims.map((c) => <li key={c.type + c.text}><strong>{c.text}</strong>: {c.reason}</li>)}</ul>
              </Alert>
            )}
            <Button variant="ghost" size="sm" className="mt-2" disabled={letter.trim().length < 50} loading={saveDraft.isPending} onClick={() => saveDraft.mutate()}>Save draft</Button>
            {draft && <span className="ml-2 text-xs text-text-muted">Version {draft.version_number}</span>}
          </Card>
          <Card>
            <h2 className="font-semibold">Resume</h2>
            {p.resumes.length === 0 ? <p className="mt-2 text-sm text-text-muted">No processed resume. You can still apply with your profile, or <Link className="text-primary underline" href="/candidate/resumes">upload one</Link>.</p> : (
              <Field label="Attach resume">{(a) => <Select {...a} value={resumeId} onChange={(e) => setResumeId(e.target.value)}><option value="">Don’t attach a resume</option>{p.resumes.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</Select>}</Field>
            )}
          </Card>
        </div>
        <Card className="h-fit">
          <h2 className="font-semibold">What the employer will see</h2>
          <ul className="mt-3 space-y-1 text-sm">
            <li><span className="text-text-muted">Name:</span> {String(p.facts.name)}</li>
            <li><span className="text-text-muted">Headline:</span> {String(p.facts.headline ?? "—")}</li>
            <li><span className="text-text-muted">Experience:</span> {p.facts.years_experience != null ? `${p.facts.years_experience} years` : "—"}</li>
            <li><span className="text-text-muted">Skills:</span> {p.facts.skills.join(", ") || "—"}</li>
            <li><span className="text-text-muted">Your email</span> (for contact)</li>
          </ul>
          <div className="mt-3"><Badge tone="info">Relevance {p.match.relevance_score}/100</Badge></div>
          <p className="mt-2 text-xs text-text-muted">The employer also sees this relevance summary as an advisory signal.</p>
          <label className="mt-4 flex gap-2 text-sm"><input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} className="mt-1" />I reviewed this application and confirm it is accurate.</label>
          <Button className="mt-4 w-full" disabled={!approved} onClick={() => setConfirmOpen(true)}>Submit application</Button>
        </Card>
      </div>
      <ConfirmDialog open={confirmOpen} title="Submit this application?" confirmLabel="Submit" loading={submit.isPending}
        description={`Your profile${resumeId ? ", selected resume" : ""}${letter.trim() ? " and cover letter" : ""} will be shared with ${p.job.company.name}.`}
        onClose={() => setConfirmOpen(false)} onConfirm={() => submit.mutate()}>
        {claims && claims.length > 0 && <p className="flex items-center gap-2 text-sm text-warning"><AlertTriangle className="h-4 w-4" aria-hidden />{claims.length} statement(s) could not be verified against your profile.</p>}
      </ConfirmDialog>
    </>
  );
}
