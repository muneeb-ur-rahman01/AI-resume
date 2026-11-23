// API response types (mirror services/api/careerpilot/api/schemas.py).

export type Me = { id: string; email: string; full_name: string; roles: string[]; email_verified: boolean };
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type Skill = { id: string; name: string; years: number | null; status: string };
export type Experience = {
  id: string; title: string; company: string; location: string | null; start_date: string | null;
  end_date: string | null; is_current: boolean; description: string | null; status: string;
};
export type Education = {
  id: string; institution: string; degree: string | null; field_of_study: string | null;
  start_date: string | null; end_date: string | null; status: string;
};
export type Preferences = {
  desired_titles: string[]; employment_types: string[]; work_arrangements: string[];
  preferred_locations: string[]; willing_to_relocate: boolean | null; min_salary: number | null;
  salary_currency: string | null; available_from: string | null;
};
export type Profile = {
  full_name: string; email: string; headline: string | null; summary: string | null;
  location_city: string | null; location_country: string | null; phone: string | null; links: string[];
  years_experience: number | null; years_experience_confirmed: number | null; onboarding_completed: boolean;
  skills: Skill[]; experiences: Experience[]; educations: Education[]; preferences: Preferences | null;
  completeness: { checks: Record<string, boolean>; percent: number };
};

export type Resume = {
  id: string; label: string; is_primary: boolean; status: "queued" | "processing" | "completed" | "failed";
  status_detail: string | null; filename: string; mime_type: string; size_bytes: number;
  extraction_method: string | null; model_name: string | null; page_count: number | null;
  created_at: string; processed_at: string | null;
};
export type Fact = {
  id: string; fact_type: string; value: Record<string, unknown>; source_text: string | null;
  source_section: string | null; confidence: number | null; method: string; status: string;
  schema_version: string; created_at: string;
};
export type ResumeDetail = Resume & { facts: Fact[]; warnings: string[] };

export type CompanyBrief = { id: string; name: string; verification_status: string };
export type JobSummary = {
  id: string; title: string; employment_type: string; work_arrangement: string; location_city: string | null;
  location_country: string | null; salary_min: number | null; salary_max: number | null;
  salary_currency: string | null; status: string; published_at: string | null;
  application_deadline: string | null; company: CompanyBrief;
};
export type Job = JobSummary & {
  department: string | null; description: string; responsibilities: string[]; benefits: string[];
  min_experience_years: number | null; max_experience_years: number | null; education_requirement: string | null;
  timezone: string | null; openings: number; external_apply_url: string | null; created_at: string;
  updated_at: string; version: number; skills: { name: string; requirement: string; min_years: number | null }[];
};
export type EmployerJobRow = JobSummary & { application_count: number; created_at: string };

export type MatchComponent = { score: number | null; weight: number; detail: string };
export type Match = {
  relevance_score: number; eligibility: string; algorithm_version: string;
  components: Record<string, MatchComponent>;
  explanation: {
    summary: string; matched_required: string[]; missing_required: string[]; matched_preferred: string[];
    missing_preferred: string[]; experience: string; preferences: string[]; data_coverage: number; disclaimer: string;
  };
};
export type Recommendations = {
  items: { job: JobSummary; match: Match }[]; profile_ready: boolean; hidden_ineligible: number; algorithm_version: string;
};

export type Claim = { type: string; text: string; reason: string };
export type CoverLetter = {
  id: string; job_id: string; version_number: number; content: string; generated_by: string | null;
  unsupported_claims: Claim[]; created_at: string;
};
export type HistoryItem = { from_status: string | null; to_status: string; actor_type: string; created_at: string; note?: string | null };
export type Interview = { id: string; starts_at: string; duration_minutes: number; location_or_link: string | null; status: string };
export type AppDoc = { kind: string; content: string; generated_by: string | null; unsupported_claims: Claim[] };
export type Application = {
  id: string; status: string; submitted_at: string | null; created_at: string; job: JobSummary;
  history: HistoryItem[]; documents: AppDoc[]; interviews: Interview[]; resume_label: string | null;
};
export type Preview = {
  job: Job; facts: Record<string, unknown> & { skills: string[] }; resumes: Resume[];
  cover_letter_draft: CoverLetter | null; match: Match; already_applied: boolean; external_apply_url: string | null;
};

export type Company = {
  id: string; name: string; slug: string; website: string | null; email_domain: string | null;
  description: string | null; industry: string | null; size_range: string | null; headquarters: string | null;
  verification_status: string; verified_at: string | null; created_at: string; my_role?: string;
};
export type Verification = {
  id: string; status: string; method: string; signals: Record<string, unknown>; evidence_note: string | null;
  decision_reason: string | null; created_at: string; reviewed_at: string | null;
};
export type EmployerAppRow = {
  id: string; status: string; submitted_at: string | null; first_viewed_at: string | null; candidate_name: string;
  candidate_headline: string | null; relevance_score: number | null; eligibility: string | null;
};
export type EmployerAppDetail = EmployerAppRow & {
  job: JobSummary; candidate: Record<string, unknown>; relevance: { score: number; eligibility: string; explanation: Match["explanation"] } | null;
  documents: AppDoc[]; history: HistoryItem[]; interviews: Interview[]; has_resume: boolean; allowed_transitions: string[];
};
export type Notification = {
  id: string; kind: string; title: string; body: string; link: string | null; read_at: string | null;
  created_at: string; email_status: string;
};
export type SessionInfo = { id: string; created_at: string; last_seen_at: string; expires_at: string; user_agent: string | null; ip_prefix: string | null; current: boolean };
