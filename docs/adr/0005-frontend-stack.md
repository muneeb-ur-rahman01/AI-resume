# ADR 0005: Next.js App Router with a small in-house accessible component set

- Status: Accepted (2026-11-17)

## Decision

Next.js 16 (App Router), React 19, TypeScript strict, Tailwind CSS 4, TanStack Query for server state, React Hook
Form + Zod for complex forms, Lucide icons, Vitest + Testing Library, Playwright.

Instead of generating shadcn/ui components (the CLI needs network access and a separate init step), the UI uses a
small set of equivalent accessible primitives in `src/components/ui.tsx` (Button, Field, Input, Select, Textarea,
Card, Badge, Alert, Skeleton, EmptyState, ErrorState, ConfirmDialog on native `<dialog>`, MatchScore). They follow
the same token-driven, Radix-free approach and can be replaced by shadcn/ui components later.

Most authenticated pages are Client Components because they depend on the session cookie and live data. The
landing page is a Server Component.

TypeScript is pinned to 6.x because `typescript-eslint` does not yet support TypeScript 7.

Recharts is not installed yet: dashboards currently show numeric stat tiles only.

## Consequences

Fewer dependencies. Component coverage is narrower than shadcn/ui (no drawer, dropdown menu or tooltip yet).
