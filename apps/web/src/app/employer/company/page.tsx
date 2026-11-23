"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useToast } from "@/components/providers";
import { Alert, Badge, Button, Card, ErrorState, Field, Input, LoadingBlock, PageHeader, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useMyCompany } from "@/lib/employer";
import { dateTime, label, STATUS_TONE } from "@/lib/format";
import type { Company, Verification } from "@/lib/types";

function CreateCompany() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", website: "", email_domain: "", industry: "", headquarters: "", description: "" });
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api<Company>("/employer/companies", { method: "POST", body: Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null])) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-companies"] }),
    onError: (e) => setError(errorMessage(e)),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <Card>
      <h2 className="font-semibold">Create your company</h2>
      <form className="mt-4 grid gap-4 md:grid-cols-2" onSubmit={(e: FormEvent) => { e.preventDefault(); setError(null); create.mutate(); }}>
        <Field label="Company name" required>{(a) => <Input {...a} required minLength={2} value={form.name} onChange={set("name")} />}</Field>
        <Field label="Website">{(a) => <Input {...a} type="url" placeholder="https://example.com" value={form.website} onChange={set("website")} />}</Field>
        <Field label="Company email domain" hint="e.g. example.com. Used as one verification signal.">{(a) => <Input {...a} value={form.email_domain} onChange={set("email_domain")} />}</Field>
        <Field label="Industry">{(a) => <Input {...a} value={form.industry} onChange={set("industry")} />}</Field>
        <Field label="Headquarters">{(a) => <Input {...a} value={form.headquarters} onChange={set("headquarters")} />}</Field>
        <div className="md:col-span-2"><Field label="Description">{(a) => <Textarea {...a} maxLength={5000} value={form.description} onChange={set("description")} />}</Field></div>
        {error && <div className="md:col-span-2"><Alert tone="danger">{error}</Alert></div>}
        <div><Button type="submit" loading={create.isPending}>Create company</Button></div>
      </form>
    </Card>
  );
}

function VerificationCard({ company }: { company: Company }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState("");
  const history = useQuery({ queryKey: ["verification", company.id], queryFn: () => api<Verification[]>(`/employer/companies/${company.id}/verification`) });
  const request = useMutation({
    mutationFn: () => api<Verification>(`/employer/companies/${company.id}/verification`, { method: "POST", body: { evidence_note: note || null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["my-companies"] }); qc.invalidateQueries({ queryKey: ["verification", company.id] }); toast("Verification requested."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const canRequest = ["unverified", "rejected"].includes(company.verification_status) && company.my_role === "owner";
  return (
    <Card>
      <div className="flex items-center justify-between"><h2 className="font-semibold">Verification</h2><Badge tone={STATUS_TONE[company.verification_status]}>{label(company.verification_status)}</Badge></div>
      <p className="mt-2 text-sm text-text-muted">A CareerPilot administrator reviews each request. Matching your sign-in email domain to the company domain is recorded as one signal; it is not proof of legal identity on its own.</p>
      {canRequest && (
        <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); request.mutate(); }}>
          <Field label="Notes for the reviewer" hint="e.g. your role, a public company registry link. Do not upload identity documents.">{(a) => <Textarea {...a} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          <Button type="submit" loading={request.isPending}>Request verification</Button>
        </form>
      )}
      {history.data && history.data.length > 0 && (
        <ul className="mt-4 divide-y divide-border text-sm">
          {history.data.map((v) => (
            <li key={v.id} className="py-2">
              <span className="font-medium">{label(v.status)}</span> · requested {dateTime(v.created_at)}
              {v.decision_reason && <p className="text-text-muted">Reviewer note: {v.decision_reason}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function CompanyPage() {
  const { company, isLoading, isError, error } = useMyCompany();
  if (isLoading) return <LoadingBlock />;
  if (isError) return <ErrorState error={error} />;
  return (
    <>
      <PageHeader title="Company" description="Your company profile and verification status." />
      {!company ? <CreateCompany /> : (
        <div className="space-y-6">
          <Card>
            <h2 className="font-semibold">{company.name}</h2>
            <dl className="mt-3 grid gap-2 text-sm md:grid-cols-2">
              <div><dt className="text-text-muted">Website</dt><dd>{company.website ?? "—"}</dd></div>
              <div><dt className="text-text-muted">Email domain</dt><dd>{company.email_domain ?? "—"}</dd></div>
              <div><dt className="text-text-muted">Industry</dt><dd>{company.industry ?? "—"}</dd></div>
              <div><dt className="text-text-muted">Your role</dt><dd>{label(company.my_role)}</dd></div>
            </dl>
            {company.description && <p className="mt-3 whitespace-pre-line text-sm">{company.description}</p>}
          </Card>
          <VerificationCard company={company} />
        </div>
      )}
    </>
  );
}
