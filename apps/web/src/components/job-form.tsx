"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { api, errorMessage } from "@/lib/api";
import { jobSchema, splitList, type JobValues } from "@/lib/schemas";
import type { Job } from "@/lib/types";
import { Alert, Button, Card, Field, Input, Select, Textarea } from "./ui";

type Parsed = {
  required_skills: string[]; preferred_skills: string[]; min_experience_years: number | null; max_experience_years: number | null;
  employment_type: string | null; work_arrangement: string | null; responsibilities: string[]; warnings: string[]; is_mock: boolean; model: string;
};

export function toPayload(v: JobValues) {
  const parsed = jobSchema.parse(v);
  const str = (s?: string) => (s && s.trim() ? s.trim() : null);
  return {
    title: parsed.title, department: str(parsed.department), description: parsed.description,
    required_skills: splitList(parsed.required_skills).map((name) => ({ name })),
    preferred_skills: splitList(parsed.preferred_skills).map((name) => ({ name })),
    min_experience_years: parsed.min_experience_years, max_experience_years: parsed.max_experience_years,
    employment_type: parsed.employment_type, work_arrangement: parsed.work_arrangement,
    location_city: str(parsed.location_city), location_country: str(parsed.location_country),
    salary_min: parsed.salary_min, salary_max: parsed.salary_max, salary_currency: str(parsed.salary_currency),
    application_deadline: str(parsed.application_deadline), external_apply_url: str(parsed.external_apply_url),
    responsibilities: [], benefits: [], openings: 1,
  };
}

export function jobToValues(j: Job): JobValues {
  return {
    title: j.title, department: j.department ?? "", description: j.description,
    required_skills: j.skills.filter((s) => s.requirement === "required").map((s) => s.name).join(", "),
    preferred_skills: j.skills.filter((s) => s.requirement === "preferred").map((s) => s.name).join(", "),
    min_experience_years: j.min_experience_years, max_experience_years: j.max_experience_years,
    employment_type: j.employment_type as JobValues["employment_type"], work_arrangement: j.work_arrangement as JobValues["work_arrangement"],
    location_city: j.location_city ?? "", location_country: j.location_country ?? "", salary_min: j.salary_min, salary_max: j.salary_max,
    salary_currency: j.salary_currency ?? "", application_deadline: j.application_deadline ?? "", external_apply_url: j.external_apply_url ?? "",
  };
}

export function JobForm({ initial, submitLabel, onSubmit, error }: {
  initial?: JobValues; submitLabel: string; error?: string | null; onSubmit: (payload: ReturnType<typeof toPayload>) => Promise<unknown>;
}) {
  const { register, handleSubmit, setValue, getValues, formState } = useForm<JobValues>({
    resolver: zodResolver(jobSchema),
    defaultValues: initial ?? { employment_type: "full_time", work_arrangement: "remote", required_skills: "", preferred_skills: "", title: "", description: "" },
  });
  const [parsed, setParsed] = useState<Parsed | null>(null);
  const parse = useMutation({
    mutationFn: () => api<Parsed>("/employer/jobs/parse", { method: "POST", body: { text: getValues("description") } }),
    onSuccess: setParsed,
  });
  function applyParsed() {
    if (!parsed) return;
    setValue("required_skills", parsed.required_skills.join(", "));
    setValue("preferred_skills", parsed.preferred_skills.join(", "));
    if (parsed.min_experience_years != null) setValue("min_experience_years", parsed.min_experience_years);
    if (parsed.max_experience_years != null) setValue("max_experience_years", parsed.max_experience_years);
    if (parsed.employment_type) setValue("employment_type", parsed.employment_type as JobValues["employment_type"]);
    if (parsed.work_arrangement) setValue("work_arrangement", parsed.work_arrangement as JobValues["work_arrangement"]);
    setParsed(null);
  }
  const e = formState.errors;
  return (
    <form noValidate onSubmit={handleSubmit((v) => onSubmit(toPayload(v)))} className="space-y-6">
      <Card className="space-y-4">
        <h2 className="font-semibold">Role</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Job title" required error={e.title?.message}>{(a) => <Input {...a} {...register("title")} />}</Field>
          <Field label="Department">{(a) => <Input {...a} {...register("department")} />}</Field>
        </div>
        <Field label="Description" required error={e.description?.message}>{(a) => <Textarea {...a} className="min-h-48" {...register("description")} />}</Field>
        <div>
          <Button type="button" variant="secondary" loading={parse.isPending} onClick={() => parse.mutate()}><Sparkles className="h-4 w-4" aria-hidden />Suggest requirements from description</Button>
          {parse.isError && <Alert tone="danger" className="mt-2">{errorMessage(parse.error)}</Alert>}
        </div>
        {parsed && (
          <Alert tone="info" title="Suggested requirements: review before applying">
            {parsed.is_mock && <p className="font-medium text-warning">Generated by the development mock provider, not a real AI model.</p>}
            <p><strong>Required:</strong> {parsed.required_skills.join(", ") || "none detected"}</p>
            <p><strong>Preferred:</strong> {parsed.preferred_skills.join(", ") || "none detected"}</p>
            {parsed.min_experience_years != null && <p><strong>Experience:</strong> {parsed.min_experience_years}+ years</p>}
            {parsed.warnings.map((w) => <p key={w} className="text-warning">{w}</p>)}
            <div className="mt-2 flex gap-2"><Button type="button" size="sm" onClick={applyParsed}>Use these suggestions</Button><Button type="button" size="sm" variant="ghost" onClick={() => setParsed(null)}>Dismiss</Button></div>
          </Alert>
        )}
      </Card>
      <Card className="space-y-4">
        <h2 className="font-semibold">Requirements</h2>
        <Field label="Required skills" hint="Comma-separated. Candidates without these are not rejected automatically; gaps are shown to you." error={e.required_skills?.message}>{(a) => <Input {...a} {...register("required_skills")} />}</Field>
        <Field label="Preferred skills" hint="Comma-separated nice-to-haves.">{(a) => <Input {...a} {...register("preferred_skills")} />}</Field>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Minimum years of experience" error={e.min_experience_years?.message}>{(a) => <Input {...a} type="number" min={0} step={0.5} {...register("min_experience_years")} />}</Field>
          <Field label="Maximum years of experience" error={e.max_experience_years?.message}>{(a) => <Input {...a} type="number" min={0} step={0.5} {...register("max_experience_years")} />}</Field>
        </div>
      </Card>
      <Card className="space-y-4">
        <h2 className="font-semibold">Logistics</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Employment type" required>{(a) => <Select {...a} {...register("employment_type")}><option value="full_time">Full time</option><option value="part_time">Part time</option><option value="contract">Contract</option><option value="internship">Internship</option><option value="temporary">Temporary</option></Select>}</Field>
          <Field label="Work arrangement" required>{(a) => <Select {...a} {...register("work_arrangement")}><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">Onsite</option></Select>}</Field>
          <Field label="Application deadline">{(a) => <Input {...a} type="date" {...register("application_deadline")} />}</Field>
          <Field label="City">{(a) => <Input {...a} {...register("location_city")} />}</Field>
          <Field label="Country code" error={e.location_country?.message}>{(a) => <Input {...a} maxLength={2} placeholder="US" {...register("location_country")} />}</Field>
          <div />
          <Field label="Salary min" error={e.salary_min?.message}>{(a) => <Input {...a} type="number" min={0} {...register("salary_min")} />}</Field>
          <Field label="Salary max" error={e.salary_max?.message}>{(a) => <Input {...a} type="number" min={0} {...register("salary_max")} />}</Field>
          <Field label="Currency" error={e.salary_currency?.message}>{(a) => <Input {...a} maxLength={3} placeholder="USD" {...register("salary_currency")} />}</Field>
        </div>
        <Field label="External application URL (optional)" hint="If set, candidates apply on your site and CareerPilot only links to it." error={e.external_apply_url?.message}>{(a) => <Input {...a} type="url" {...register("external_apply_url")} />}</Field>
      </Card>
      {error && <Alert tone="danger">{error}</Alert>}
      <Button type="submit" loading={formState.isSubmitting}>{submitLabel}</Button>
    </form>
  );
}
