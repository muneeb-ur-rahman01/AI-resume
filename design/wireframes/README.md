# Wireframes

Low-fidelity layout specifications. The implemented screens in `apps/web` are the high-fidelity reference.
Screenshots of the running app are in [`../screens/`](../screens/) when captured.

## Candidate dashboard (desktop ≥1024 px; mobile stacks the columns)

```
┌ Header: wordmark | Dashboard  Recommended  Search  Resumes  Profile  Applications | 🔔 ⚙ ⎋ ┐
│ H1 Welcome, Ada                                                                        │
│ ┌ Profile strength ┐ ┌ Top matches ───────────────────────────────── See all ┐        │
│ │ 60%              │ │ [JobCard: title · company · location · pay | 82/100 ] │        │
│ │ ✓ headline       │ │ [JobCard ...                                        ] │        │
│ │ ○ preferences →  │ │ [JobCard ...                                        ] │        │
│ │ [Upload resume]  │ └───────────────────────────────────────────────────────┘        │
│ └──────────────────┘                                                                   │
│ ┌ Recent applications ───────────────────────────────────────────── View all ┐         │
│ │ Senior Python Engineer · Acme      12 Nov 2026   [Shortlisted]              │         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## Job detail + match explanation

```
H1 Title · company [Verified] · location · pay · type      [Prepare application] [Save] [Report]
┌ Why this job matches ──────────────────────────── 82/100  [Meets requirements] ┐
│ Requirements you meet        │ Not in your confirmed profile                    │
│ ✓ Python (required)          │ ? Terraform (preferred)                          │
│ Experience: You have about 6 years; the job asks for 4+.                         │
│ ▸ How the score is calculated (table: factor | weight | score | detail)          │
└──────────────────────────────────────────────────────────────────────────────────┘
About the role · Responsibilities · Skills badges · Benefits
```

## Application preview (apply)

```
H1 Apply: Title                                           ┌ What the employer will see ┐
┌ Cover letter (optional) ────────────────────────────┐   │ Name, headline, years,     │
│ Tone [Professional ▾] [Draft with AI]               │   │ skills, contact email      │
│ [ textarea ................................. ]      │   │ Relevance 82/100           │
│ ⚠ Check these statements: "40" not in profile      │   │ ☐ I reviewed ... accurate  │
│ [Save draft] v2                                      │   │ [Submit application]       │
└──────────────────────────────────────────────────────┘   └────────────────────────────┘
┌ Resume: [Primary CV ▾] ┐
```

## Employer applicant detail

```
← Job title
H1 Candidate name · headline        [Submitted] [Shortlist] [Move to interview] [Reject]
┌ Candidate profile (as submitted) ┐ ┌ Timeline ┐
│ contact, skills, roles, education│ │ ● Submitted  (by candidate)
│ Download resume                  │ │ ● Shortlisted (note)
├ Cover letter ────────────────────┤ ├ Schedule interview ┐
├ Relevance summary (advisory) ────┤ │ date, duration, link│
```

Mobile (<768 px): single column, header nav becomes a horizontally scrollable row, side panels move below the
main content, tables scroll horizontally.
