# Component inventory

| Component | File | Variants / states | Notes |
| --- | --- | --- | --- |
| Button | `components/ui.tsx` | primary, secondary, ghost, danger; md (40 px) / sm (32 px); loading (spinner + `aria-busy`), disabled | |
| LinkButton | `ui.tsx` | same variants | Next `<Link>` styled as a button |
| Input / Textarea / Select | `ui.tsx` | default, invalid (`aria-invalid` → danger border), disabled | |
| Field | `ui.tsx` | label, required marker, hint, error | Wires `id`, `aria-describedby`, `aria-invalid`; error has `role="alert"` |
| Card | `ui.tsx` | — | 12 px radius, 1 px border, subtle shadow |
| PageHeader | `ui.tsx` | title, description, actions | |
| Badge | `ui.tsx` | neutral, info, success, warning, danger | Always has text |
| Alert | `ui.tsx` | info, success, warning, danger, neutral; optional title | `role="alert"` for danger, `status` otherwise |
| Skeleton / LoadingBlock | `ui.tsx` | — | LoadingBlock announces "Loading…" to screen readers |
| EmptyState | `ui.tsx` | icon, title, description, action | |
| ErrorState | `ui.tsx` | generic with retry; 403 and 404 variants | |
| ConfirmDialog | `ui.tsx` | primary/danger, loading, custom body | Native `<dialog>`: focus trap, Esc closes |
| MatchScore | `ui.tsx` | 0-100 | Numeric label + bar; color is secondary |
| Toast | `components/providers.tsx` | success, danger, info | `aria-live="polite"`, 5 s |
| AppShell | `components/app-shell.tsx` | candidate, employer, admin nav; mobile nav | Skip link, unread indicator, role guard (UX only) |
| JobCard | `components/job-card.tsx` | with/without match | |
| MatchExplanation | `components/match-explanation.tsx` | — | Requirements met/not found, experience, preference conflicts, component table |
| Timeline | `components/timeline.tsx` | with/without notes | Ordered list |
| JobForm | `components/job-form.tsx` | create/edit | RHF + Zod; AI suggestions panel |
| File upload | `app/candidate/resumes/page.tsx` | idle, dragging, uploading, error | Keyboard-accessible "Choose file" button |

Planned: Drawer, DropdownMenu, Tooltip, Tabs, Pagination component (pagination currently inline on job search),
resume preview, charts.
