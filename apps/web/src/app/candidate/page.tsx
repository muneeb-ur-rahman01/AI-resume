"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { JobCard } from "@/components/job-card";
import { Badge, Card, EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, STATUS_TEXT, STATUS_TONE } from "@/lib/format";
import type { Application, Page, Profile, Recommendations, Resume } from "@/lib/types";

const CHECK_LABELS: Record<string, { text: string; href: string }> = {
  headline: { text: "Add a headline", href: "/candidate/profile" },
  skills: { text: "Confirm at least 3 skills", href: "/candidate/resumes" },
  experience: { text: "Confirm your work experience", href: "/candidate/resumes" },
  preferences: { text: "Set job preferences", href: "/candidate/profile#preferences" },
  location: { text: "Add your location", href: "/candidate/profile" },
};

export default function CandidateDashboard() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: () => api<Profile>("/candidate/profile") });
  const resumes = useQuery({ queryKey: ["resumes"], queryFn: () => api<Resume[]>("/candidate/resumes") });
  const recs = useQuery({ queryKey: ["recommendations", 3], queryFn: () => api<Recommendations>("/candidate/recommendations?limit=3") });
  const apps = useQuery({ queryKey: ["applications", 1], queryFn: () => api<Page<Application>>("/candidate/applications?page_size=5") });

  if (profile.isLoading) return <LoadingBlock />;
  if (profile.isError) return <ErrorState error={profile.error} onRetry={() => profile.refetch()} />;
  const p = profile.data!;

  return (
    <>
      <PageHeader title={`Welcome, ${p.full_name.split(" ")[0]}`} description="Your profile, matches and applications at a glance." />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <h2 className="font-semibold">Profile strength</h2>
          <p className="mt-1 text-3xl font-semibold">{p.completeness.percent}%</p>
          <ul className="mt-4 space-y-2 text-sm">
            {Object.entries(p.completeness.checks).map(([key, done]) => (
              <li key={key} className="flex items-center gap-2">
                {done ? <CheckCircle2 className="h-4 w-4 text-success" aria-hidden /> : <Circle className="h-4 w-4 text-text-muted" aria-hidden />}
                {done ? <span>{CHECK_LABELS[key]?.text}</span> : <Link className="text-primary underline" href={CHECK_LABELS[key]?.href ?? "#"}>{CHECK_LABELS[key]?.text}</Link>}
                <span className="sr-only">{done ? "(done)" : "(to do)"}</span>
              </li>
            ))}
          </ul>
          {resumes.data && resumes.data.length === 0 && (
            <LinkButton href="/candidate/resumes" className="mt-5 w-full">Upload your resume</LinkButton>
          )}
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Top matches</h2>
            <Link href="/candidate/recommendations" className="text-sm text-primary underline">See all</Link>
          </div>
          {recs.isLoading && <LoadingBlock label="Loading matches" />}
          {recs.isError && <ErrorState error={recs.error} onRetry={() => recs.refetch()} />}
          {recs.data && recs.data.items.length === 0 && (
            <EmptyState title={recs.data.profile_ready ? "No matching jobs right now" : "Confirm your skills to get matches"}
              description={recs.data.profile_ready ? "We'll show new jobs as employers publish them. You can also search all jobs." : "Upload a resume and confirm the extracted skills, or add skills manually."}
              action={<LinkButton href={recs.data.profile_ready ? "/jobs" : "/candidate/resumes"} variant="secondary">{recs.data.profile_ready ? "Search jobs" : "Go to resumes"}</LinkButton>} />
          )}
          {recs.data?.items.map((r) => <JobCard key={r.job.id} job={r.job} match={r.match} />)}
        </div>
      </div>

      <Card className="mt-6">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Recent applications</h2>
          <Link href="/candidate/applications" className="text-sm text-primary underline">View all</Link>
        </div>
        {apps.isLoading && <LoadingBlock />}
        {apps.data && apps.data.items.length === 0 && <p className="mt-3 text-sm text-text-muted">You haven’t applied to any jobs yet.</p>}
        <ul className="mt-3 divide-y divide-border">
          {apps.data?.items.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
              <Link href={`/candidate/applications/${a.id}`} className="font-medium hover:underline">{a.job.title} · {a.job.company.name}</Link>
              <span className="flex items-center gap-3 text-text-muted">{date(a.submitted_at)}<Badge tone={STATUS_TONE[a.status]}>{STATUS_TEXT[a.status] ?? label(a.status)}</Badge></span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
