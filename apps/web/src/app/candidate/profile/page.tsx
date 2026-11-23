"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useToast } from "@/components/providers";
import { Badge, Button, Card, ErrorState, Field, Input, LoadingBlock, PageHeader, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { date } from "@/lib/format";
import type { Profile } from "@/lib/types";

function useSave(path: string, method: "PUT" | "POST" | "DELETE" = "PUT", success = "Saved.") {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body?: unknown) => api<Profile>(path, { method, body }),
    onSuccess: (p) => { qc.setQueryData(["profile"], p); qc.invalidateQueries({ queryKey: ["recommendations"] }); toast(success); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
}

function BasicsCard({ p }: { p: Profile }) {
  const [form, setForm] = useState({ headline: p.headline ?? "", summary: p.summary ?? "", location_city: p.location_city ?? "", location_country: p.location_country ?? "", years_experience_confirmed: p.years_experience_confirmed?.toString() ?? "" });
  const save = useSave("/candidate/profile");
  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate({
      headline: form.headline || null, summary: form.summary || null, location_city: form.location_city || null,
      location_country: form.location_country ? form.location_country.toUpperCase() : null,
      years_experience_confirmed: form.years_experience_confirmed === "" ? null : Number(form.years_experience_confirmed),
    });
  }
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <Card>
      <h2 className="font-semibold">Basics</h2>
      <form onSubmit={submit} className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2"><Field label="Headline">{(a) => <Input {...a} maxLength={200} value={form.headline} onChange={set("headline")} placeholder="e.g. Senior Backend Engineer" />}</Field></div>
        <div className="md:col-span-2"><Field label="Summary">{(a) => <Textarea {...a} maxLength={2000} value={form.summary} onChange={set("summary")} />}</Field></div>
        <Field label="City">{(a) => <Input {...a} value={form.location_city} onChange={set("location_city")} />}</Field>
        <Field label="Country code" hint="2 letters, e.g. US, DE, PK">{(a) => <Input {...a} maxLength={2} value={form.location_country} onChange={set("location_country")} />}</Field>
        <Field label="Years of experience (optional)" hint={`Calculated from your roles: ${p.years_experience ?? "unknown"}. Set this only to override.`}>
          {(a) => <Input {...a} type="number" min={0} max={60} step={0.5} value={form.years_experience_confirmed} onChange={set("years_experience_confirmed")} />}
        </Field>
        <div className="md:col-span-2"><Button type="submit" loading={save.isPending}>Save basics</Button></div>
      </form>
    </Card>
  );
}

function SkillsCard({ p }: { p: Profile }) {
  const [name, setName] = useState("");
  const add = useSave("/candidate/skills", "POST", "Skill added.");
  const qc = useQueryClient();
  const toast = useToast();
  const remove = useMutation({
    mutationFn: (id: string) => api<Profile>(`/candidate/skills/${id}`, { method: "DELETE" }),
    onSuccess: (prof) => { qc.setQueryData(["profile"], prof); qc.invalidateQueries({ queryKey: ["recommendations"] }); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  return (
    <Card>
      <h2 className="font-semibold">Skills</h2>
      <p className="text-sm text-text-muted">Only confirmed skills are used for matching and cover letters.</p>
      <ul className="mt-3 flex flex-wrap gap-2" aria-label="Your skills">
        {p.skills.length === 0 && <li className="text-sm text-text-muted">No skills yet.</li>}
        {p.skills.map((s) => (
          <li key={s.id} className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-muted py-1 pl-3 pr-1 text-sm">
            {s.name}
            <button onClick={() => remove.mutate(s.id)} className="rounded-full p-1 hover:bg-border" aria-label={`Remove ${s.name}`}><X className="h-3 w-3" aria-hidden /></button>
          </li>
        ))}
      </ul>
      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (name.trim()) add.mutate({ name: name.trim() }, { onSuccess: () => setName("") }); }}>
        <label htmlFor="new-skill" className="sr-only">Add a skill</label>
        <Input id="new-skill" value={name} onChange={(e) => setName(e.target.value)} placeholder="Add a skill, e.g. PostgreSQL" maxLength={120} />
        <Button type="submit" variant="secondary" loading={add.isPending}>Add</Button>
      </form>
    </Card>
  );
}

function ExperienceCard({ p }: { p: Profile }) {
  const empty = { title: "", company: "", start_date: "", end_date: "", is_current: false, description: "" };
  const [form, setForm] = useState(empty);
  const add = useSave("/candidate/experiences", "POST", "Experience added.");
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: string) => api<Profile>(`/candidate/experiences/${id}`, { method: "DELETE" }),
    onSuccess: (prof) => qc.setQueryData(["profile"], prof),
  });
  return (
    <Card>
      <h2 className="font-semibold">Experience</h2>
      <ul className="mt-3 divide-y divide-border">
        {p.experiences.length === 0 && <li className="py-2 text-sm text-text-muted">No experience yet.</li>}
        {p.experiences.map((x) => (
          <li key={x.id} className="flex items-start justify-between gap-3 py-3">
            <div className="text-sm">
              <p className="font-medium">{x.title} · {x.company}</p>
              <p className="text-text-muted">{date(x.start_date)} – {x.is_current ? "Present" : date(x.end_date)}</p>
              {x.description && <p className="mt-1 whitespace-pre-line text-text-muted">{x.description}</p>}
            </div>
            <Button variant="ghost" size="sm" onClick={() => remove.mutate(x.id)} aria-label={`Delete ${x.title} at ${x.company}`}><Trash2 className="h-4 w-4" aria-hidden /></Button>
          </li>
        ))}
      </ul>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-primary">Add experience</summary>
        <form className="mt-3 grid gap-3 md:grid-cols-2" onSubmit={(e) => {
          e.preventDefault();
          add.mutate({ ...form, start_date: form.start_date || null, end_date: form.is_current ? null : form.end_date || null, description: form.description || null }, { onSuccess: () => setForm(empty) });
        }}>
          <Field label="Title" required>{(a) => <Input {...a} required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
          <Field label="Company" required>{(a) => <Input {...a} required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />}</Field>
          <Field label="Start date">{(a) => <Input {...a} type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />}</Field>
          <Field label="End date">{(a) => <Input {...a} type="date" disabled={form.is_current} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />}</Field>
          <label className="flex items-center gap-2 text-sm md:col-span-2"><input type="checkbox" checked={form.is_current} onChange={(e) => setForm({ ...form, is_current: e.target.checked })} /> I currently work here</label>
          <div className="md:col-span-2"><Field label="Description">{(a) => <Textarea {...a} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />}</Field></div>
          <div><Button type="submit" loading={add.isPending}>Add experience</Button></div>
        </form>
      </details>
    </Card>
  );
}

function EducationCard({ p }: { p: Profile }) {
  const [form, setForm] = useState({ institution: "", degree: "", field_of_study: "" });
  const add = useSave("/candidate/educations", "POST", "Education added.");
  const qc = useQueryClient();
  const remove = useMutation({ mutationFn: (id: string) => api<Profile>(`/candidate/educations/${id}`, { method: "DELETE" }), onSuccess: (prof) => qc.setQueryData(["profile"], prof) });
  return (
    <Card>
      <h2 className="font-semibold">Education</h2>
      <ul className="mt-3 divide-y divide-border">
        {p.educations.length === 0 && <li className="py-2 text-sm text-text-muted">No education yet.</li>}
        {p.educations.map((x) => (
          <li key={x.id} className="flex items-center justify-between py-2 text-sm">
            <span><span className="font-medium">{[x.degree, x.field_of_study].filter(Boolean).join(" in ") || "Studies"}</span> · {x.institution}</span>
            <Button variant="ghost" size="sm" onClick={() => remove.mutate(x.id)} aria-label={`Delete education at ${x.institution}`}><Trash2 className="h-4 w-4" aria-hidden /></Button>
          </li>
        ))}
      </ul>
      <form className="mt-3 grid gap-3 md:grid-cols-3" onSubmit={(e) => { e.preventDefault(); add.mutate({ institution: form.institution, degree: form.degree || null, field_of_study: form.field_of_study || null }, { onSuccess: () => setForm({ institution: "", degree: "", field_of_study: "" }) }); }}>
        <Field label="Institution" required>{(a) => <Input {...a} required value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} />}</Field>
        <Field label="Degree">{(a) => <Input {...a} value={form.degree} onChange={(e) => setForm({ ...form, degree: e.target.value })} />}</Field>
        <Field label="Field of study">{(a) => <Input {...a} value={form.field_of_study} onChange={(e) => setForm({ ...form, field_of_study: e.target.value })} />}</Field>
        <div><Button type="submit" variant="secondary" loading={add.isPending}>Add education</Button></div>
      </form>
    </Card>
  );
}

const TYPES = ["full_time", "part_time", "contract", "internship", "temporary"];
const ARR = ["remote", "hybrid", "onsite"];

function PreferencesCard({ p }: { p: Profile }) {
  const pr = p.preferences;
  const [form, setForm] = useState({
    desired_titles: (pr?.desired_titles ?? []).join(", "), employment_types: pr?.employment_types ?? [], work_arrangements: pr?.work_arrangements ?? [],
    willing_to_relocate: pr?.willing_to_relocate == null ? "" : String(pr.willing_to_relocate), min_salary: pr?.min_salary?.toString() ?? "", salary_currency: pr?.salary_currency ?? "",
  });
  const save = useSave("/candidate/preferences");
  const toggle = (key: "employment_types" | "work_arrangements", v: string) =>
    setForm((f) => ({ ...f, [key]: f[key].includes(v) ? f[key].filter((x) => x !== v) : [...f[key], v] }));
  return (
    <Card id="preferences">
      <h2 className="font-semibold">Job preferences</h2>
      <form className="mt-4 space-y-4" onSubmit={(e) => {
        e.preventDefault();
        save.mutate({
          desired_titles: form.desired_titles.split(",").map((s) => s.trim()).filter(Boolean), employment_types: form.employment_types, work_arrangements: form.work_arrangements,
          preferred_locations: pr?.preferred_locations ?? [], willing_to_relocate: form.willing_to_relocate === "" ? null : form.willing_to_relocate === "true",
          min_salary: form.min_salary === "" ? null : Number(form.min_salary), salary_currency: form.salary_currency ? form.salary_currency.toUpperCase() : null, available_from: pr?.available_from ?? null,
        });
      }}>
        <Field label="Desired job titles" hint="Comma-separated">{(a) => <Input {...a} value={form.desired_titles} onChange={(e) => setForm({ ...form, desired_titles: e.target.value })} />}</Field>
        <fieldset><legend className="text-sm font-medium">Employment types</legend>
          <div className="mt-2 flex flex-wrap gap-3">{TYPES.map((t) => <label key={t} className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={form.employment_types.includes(t)} onChange={() => toggle("employment_types", t)} />{t.replace("_", " ")}</label>)}</div>
        </fieldset>
        <fieldset><legend className="text-sm font-medium">Work arrangements</legend>
          <div className="mt-2 flex flex-wrap gap-3">{ARR.map((t) => <label key={t} className="flex items-center gap-1.5 text-sm"><input type="checkbox" checked={form.work_arrangements.includes(t)} onChange={() => toggle("work_arrangements", t)} />{t}</label>)}</div>
        </fieldset>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Open to relocation">{(a) => <Select {...a} value={form.willing_to_relocate} onChange={(e) => setForm({ ...form, willing_to_relocate: e.target.value })}><option value="">Not specified</option><option value="true">Yes</option><option value="false">No</option></Select>}</Field>
          <Field label="Minimum salary">{(a) => <Input {...a} type="number" min={0} value={form.min_salary} onChange={(e) => setForm({ ...form, min_salary: e.target.value })} />}</Field>
          <Field label="Currency" hint="e.g. USD">{(a) => <Input {...a} maxLength={3} value={form.salary_currency} onChange={(e) => setForm({ ...form, salary_currency: e.target.value })} />}</Field>
        </div>
        <Button type="submit" loading={save.isPending}>Save preferences</Button>
      </form>
    </Card>
  );
}

export default function ProfilePage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => api<Profile>("/candidate/profile") });
  if (profile.isLoading) return <LoadingBlock />;
  if (profile.isError) return <ErrorState error={profile.error} onRetry={() => profile.refetch()} />;
  const p = profile.data!;
  return (
    <>
      <PageHeader title="Profile" description="Your confirmed profile drives matching and application drafts. Correct anything that's inaccurate." actions={<Badge tone="info">{p.completeness.percent}% complete</Badge>} />
      <div className="space-y-6">
        <BasicsCard key={`b-${p.headline}-${p.location_country}`} p={p} />
        <SkillsCard p={p} />
        <ExperienceCard p={p} />
        <EducationCard p={p} />
        <PreferencesCard p={p} />
      </div>
    </>
  );
}
