"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import Link from "next/link";
import { Alert, Badge, Card, EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useMyCompany } from "@/lib/employer";
import { date, label, STATUS_TONE } from "@/lib/format";
import type { EmployerJobRow } from "@/lib/types";

export default function EmployerDashboard() {
  const { company, isLoading, isError, error } = useMyCompany();
  const jobs = useQuery({ queryKey: ["company-jobs", company?.id], queryFn: () => api<EmployerJobRow[]>(`/employer/companies/${company!.id}/jobs`), enabled: !!company });
  if (isLoading) return <LoadingBlock />;
  if (isError) return <ErrorState error={error} />;
  if (!company) return <EmptyState icon={<Building2 className="h-8 w-8" />} title="Create your company profile" description="You need a company before posting jobs." action={<LinkButton href="/employer/company">Create company</LinkButton>} />;
  return (
    <>
      <PageHeader title={company.name} description="Manage jobs and review applicants." actions={<LinkButton href="/employer/jobs/new">Post a job</LinkButton>} />
      {company.verification_status !== "verified" && (
        <Alert tone="warning" title={`Company verification: ${label(company.verification_status)}`} className="mb-6">
          Verified companies can publish jobs. <Link href="/employer/company" className="underline">Manage verification</Link>
        </Alert>
      )}
      {jobs.isLoading && <LoadingBlock />}
      {jobs.data?.length === 0 && <EmptyState title="No jobs yet" description="Create your first job posting. It stays a draft until you publish it." action={<LinkButton href="/employer/jobs/new">Post a job</LinkButton>} />}
      {jobs.data && jobs.data.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Job postings</caption>
            <thead className="border-b border-border bg-surface-muted text-text-muted"><tr><th className="px-4 py-2 font-medium">Title</th><th className="px-4 py-2 font-medium">Status</th><th className="px-4 py-2 font-medium">Applicants</th><th className="px-4 py-2 font-medium">Created</th></tr></thead>
            <tbody>
              {jobs.data.map((j) => (
                <tr key={j.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3"><Link className="font-medium hover:underline" href={`/employer/jobs/${j.id}`}>{j.title}</Link></td>
                  <td className="px-4 py-3"><Badge tone={STATUS_TONE[j.status]}>{label(j.status)}</Badge></td>
                  <td className="px-4 py-3">{j.application_count}</td>
                  <td className="px-4 py-3">{date(j.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
