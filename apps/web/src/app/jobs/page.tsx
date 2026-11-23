"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { JobCard } from "@/components/job-card";
import { Button, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { JobSummary, Page } from "@/lib/types";

type Filters = { q: string; employment_type: string; work_arrangement: string; country: string; skill: string; sort: string };
const empty: Filters = { q: "", employment_type: "", work_arrangement: "", country: "", skill: "", sort: "newest" };

export default function JobSearchPage() {
  const [draft, setDraft] = useState<Filters>(empty);
  const [filters, setFilters] = useState<Filters>(empty);
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams(Object.entries({ ...filters, page: String(page) }).filter(([, v]) => v) as [string, string][]).toString();
  const jobs = useQuery({ queryKey: ["jobs", qs], queryFn: () => api<Page<JobSummary>>(`/jobs?${qs}`), placeholderData: keepPreviousData });
  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [k]: e.target.value }));
  function submit(e: FormEvent) { e.preventDefault(); setPage(1); setFilters(draft); }
  const pages = jobs.data ? Math.max(1, Math.ceil(jobs.data.total / jobs.data.page_size)) : 1;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <p className="mb-4 text-sm"><Link href="/" className="font-semibold">CareerPilot<span className="text-primary"> AI</span></Link></p>
      <PageHeader title="Search jobs" description="Structured search across published jobs. This works even when AI features are unavailable." />
      <form onSubmit={submit} className="grid gap-3 rounded-xl border border-border bg-surface p-4 md:grid-cols-6" role="search">
        <div className="md:col-span-2"><Field label="Keywords">{(a) => <Input {...a} value={draft.q} onChange={set("q")} placeholder="Title, company or keyword" />}</Field></div>
        <Field label="Skill">{(a) => <Input {...a} value={draft.skill} onChange={set("skill")} placeholder="e.g. Python" />}</Field>
        <Field label="Type">{(a) => <Select {...a} value={draft.employment_type} onChange={set("employment_type")}><option value="">Any</option><option value="full_time">Full time</option><option value="part_time">Part time</option><option value="contract">Contract</option><option value="internship">Internship</option></Select>}</Field>
        <Field label="Arrangement">{(a) => <Select {...a} value={draft.work_arrangement} onChange={set("work_arrangement")}><option value="">Any</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">Onsite</option></Select>}</Field>
        <Field label="Country">{(a) => <Input {...a} value={draft.country} onChange={set("country")} maxLength={2} placeholder="US" />}</Field>
        <div className="flex items-end gap-2 md:col-span-6">
          <Field label="Sort">{(a) => <Select {...a} value={draft.sort} onChange={set("sort")}><option value="newest">Newest</option><option value="salary">Highest salary</option></Select>}</Field>
          <Button type="submit"><Search className="h-4 w-4" aria-hidden />Search</Button>
        </div>
      </form>
      <div className="mt-6 space-y-3" aria-live="polite">
        {jobs.isLoading && <LoadingBlock />}
        {jobs.isError && <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />}
        {jobs.data && <p className="text-sm text-text-muted">{jobs.data.total} job(s)</p>}
        {jobs.data?.items.length === 0 && <EmptyState title="No jobs match your search" description="Try removing some filters." />}
        {jobs.data?.items.map((j) => <JobCard key={j.id} job={j} />)}
      </div>
      {pages > 1 && (
        <nav aria-label="Pagination" className="mt-6 flex items-center justify-center gap-3">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-sm">Page {page} of {pages}</span>
          <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </nav>
      )}
    </div>
  );
}
