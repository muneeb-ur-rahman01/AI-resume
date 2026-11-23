import { Building2, MapPin, Wallet } from "lucide-react";
import Link from "next/link";
import { label, location, salary, STATUS_TEXT, STATUS_TONE } from "@/lib/format";
import type { JobSummary, Match } from "@/lib/types";
import { Badge, Card, MatchScore } from "./ui";

export function JobCard({ job, match, href }: { job: JobSummary; match?: Match; href?: string }) {
  const pay = salary(job.salary_min, job.salary_max, job.salary_currency);
  return (
    <Card className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h3 className="text-base font-semibold">
          <Link href={href ?? `/jobs/${job.id}`} className="hover:underline">{job.title}</Link>
        </h3>
        <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-text-muted">
          <span className="inline-flex items-center gap-1"><Building2 className="h-4 w-4" aria-hidden />{job.company.name}
            {job.company.verification_status === "verified" && <Badge tone="success" className="ml-1">Verified</Badge>}
          </span>
          <span className="inline-flex items-center gap-1"><MapPin className="h-4 w-4" aria-hidden />{location(job.location_city, job.location_country, job.work_arrangement)}</span>
          {pay && <span className="inline-flex items-center gap-1"><Wallet className="h-4 w-4" aria-hidden />{pay}</span>}
          <span>{label(job.employment_type)}</span>
        </p>
        {match && (
          <div className="mt-3 text-sm">
            <p>{match.explanation.summary}</p>
            {match.explanation.missing_required.length > 0 && (
              <p className="mt-1 text-text-muted">Not in your confirmed profile: {match.explanation.missing_required.join(", ")}</p>
            )}
          </div>
        )}
      </div>
      {match && (
        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <MatchScore score={match.relevance_score} />
          <Badge tone={STATUS_TONE[match.eligibility]}>{STATUS_TEXT[match.eligibility] ?? label(match.eligibility)}</Badge>
        </div>
      )}
    </Card>
  );
}
