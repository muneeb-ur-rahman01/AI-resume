"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { JobCard } from "@/components/job-card";
import { Alert, Button, EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Recommendations } from "@/lib/types";

export default function RecommendationsPage() {
  const [showAll, setShowAll] = useState(false);
  const qc = useQueryClient();
  const recs = useQuery({
    queryKey: ["recommendations", "all", showAll],
    queryFn: () => api<Recommendations>(`/candidate/recommendations?limit=30&include_ineligible=${showAll}`),
  });
  const dismiss = useMutation({
    mutationFn: (jobId: string) => api("/candidate/recommendation-events", { method: "POST", body: { job_id: jobId, event_type: "dismiss" } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recommendations"] }),
  });

  return (
    <>
      <PageHeader title="Recommended jobs" description="Ranked by a transparent relevance score built from your confirmed profile and preferences." />
      <Alert tone="info" className="mb-4">
        Relevance scores are heuristic ranking signals (algorithm {recs.data?.algorithm_version ?? "rules-v1"}). They are not predictions of whether you will be hired, and missing skills may simply not be in your confirmed profile yet.
      </Alert>
      {recs.isLoading && <LoadingBlock label="Finding matches" />}
      {recs.isError && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
      {recs.data && (
        <>
          {recs.data.hidden_ineligible > 0 && !showAll && (
            <p className="mb-3 text-sm text-text-muted">
              {recs.data.hidden_ineligible} job(s) hidden because they conflict with your stated preferences.{" "}
              <button className="text-primary underline" onClick={() => setShowAll(true)}>Show them</button>
            </p>
          )}
          {recs.data.items.length === 0 ? (
            <EmptyState icon={<Sparkles className="h-8 w-8" />} title={recs.data.profile_ready ? "No matches yet" : "Your profile needs confirmed skills"}
              description={recs.data.profile_ready ? "No published jobs currently match. Try the full job search." : "Upload a resume and confirm extracted skills, or add them on your profile."}
              action={<LinkButton href={recs.data.profile_ready ? "/jobs" : "/candidate/resumes"} variant="secondary">{recs.data.profile_ready ? "Search jobs" : "Upload resume"}</LinkButton>} />
          ) : (
            <ul className="space-y-3">
              {recs.data.items.map((r) => (
                <li key={r.job.id} className="relative">
                  <JobCard job={r.job} match={r.match} />
                  <div className="mt-1 flex justify-end">
                    <Button variant="ghost" size="sm" onClick={() => dismiss.mutate(r.job.id)}>Not interested</Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  );
}
