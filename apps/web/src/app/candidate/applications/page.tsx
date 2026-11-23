"use client";

import { useQuery } from "@tanstack/react-query";
import { Briefcase } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Card, EmptyState, ErrorState, Field, LinkButton, LoadingBlock, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, STATUS_TEXT, STATUS_TONE } from "@/lib/format";
import type { Application, Page } from "@/lib/types";

export default function ApplicationsPage() {
  const [status, setStatus] = useState("");
  const apps = useQuery({ queryKey: ["applications", status], queryFn: () => api<Page<Application>>(`/candidate/applications?page_size=50${status ? `&status=${status}` : ""}`) });
  return (
    <>
      <PageHeader title="Applications" description="Statuses change only when an employer updates them or you withdraw." />
      <div className="mb-4 max-w-xs">
        <Field label="Filter by status">{(a) => <Select {...a} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>{["submitted", "shortlisted", "interview", "offer", "rejected", "withdrawn", "hired"].map((s) => <option key={s} value={s}>{STATUS_TEXT[s] ?? label(s)}</option>)}
        </Select>}</Field>
      </div>
      {apps.isLoading && <LoadingBlock />}
      {apps.isError && <ErrorState error={apps.error} onRetry={() => apps.refetch()} />}
      {apps.data?.items.length === 0 && <EmptyState icon={<Briefcase className="h-8 w-8" />} title="No applications" description="When you apply to jobs, you can track them here." action={<LinkButton href="/candidate/recommendations" variant="secondary">See recommended jobs</LinkButton>} />}
      {apps.data && apps.data.items.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Your applications</caption>
            <thead className="border-b border-border bg-surface-muted text-text-muted"><tr><th className="px-4 py-2 font-medium">Job</th><th className="px-4 py-2 font-medium">Company</th><th className="px-4 py-2 font-medium">Submitted</th><th className="px-4 py-2 font-medium">Status</th></tr></thead>
            <tbody>
              {apps.data.items.map((a) => (
                <tr key={a.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3"><Link className="font-medium hover:underline" href={`/candidate/applications/${a.id}`}>{a.job.title}</Link></td>
                  <td className="px-4 py-3">{a.job.company.name}</td>
                  <td className="px-4 py-3">{date(a.submitted_at)}</td>
                  <td className="px-4 py-3"><Badge tone={STATUS_TONE[a.status]}>{STATUS_TEXT[a.status] ?? label(a.status)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
