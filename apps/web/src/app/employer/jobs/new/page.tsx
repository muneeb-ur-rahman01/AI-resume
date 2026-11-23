"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { JobForm } from "@/components/job-form";
import { EmptyState, LinkButton, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useMyCompany } from "@/lib/employer";
import type { Job } from "@/lib/types";

export default function NewJobPage() {
  const { company, isLoading } = useMyCompany();
  const router = useRouter();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  if (isLoading) return <LoadingBlock />;
  if (!company) return <EmptyState title="Create a company first" action={<LinkButton href="/employer/company">Create company</LinkButton>} />;
  return (
    <>
      <PageHeader title="Post a job" description="Jobs are saved as drafts. You can preview and publish once your company is verified." />
      <JobForm submitLabel="Save draft" error={error} onSubmit={async (payload) => {
        setError(null);
        try {
          const job = await api<Job>(`/employer/companies/${company.id}/jobs`, { method: "POST", body: payload });
          qc.invalidateQueries({ queryKey: ["company-jobs"] });
          router.push(`/employer/jobs/${job.id}`);
        } catch (e) { setError(errorMessage(e)); }
      }} />
    </>
  );
}
