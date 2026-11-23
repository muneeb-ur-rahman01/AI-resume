import { CheckCircle2, FileSearch, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";

const features = [
  { icon: FileSearch, title: "Understands your resume", body: "Upload a PDF or DOCX. We extract skills and experience with provenance, and you confirm every fact before it is used." },
  { icon: Sparkles, title: "Explains every match", body: "See which requirements you meet, what's missing, and why a job ranks where it does. Scores are relevance signals, not hiring predictions." },
  { icon: CheckCircle2, title: "You approve every application", body: "Cover letters are drafted only from facts you confirmed, unsupported claims are flagged, and nothing is sent without your confirmation." },
  { icon: ShieldCheck, title: "Private by design", body: "Resumes are stored privately, AI processing is opt-in, and you can export or delete your data at any time." },
];

export default function Landing() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5">
        <span className="text-lg font-semibold tracking-tight">CareerPilot<span className="text-primary"> AI</span></span>
        <nav aria-label="Account" className="flex items-center gap-2 text-sm">
          <Link href="/jobs" className="rounded-md px-3 py-2 hover:bg-surface-muted">Browse jobs</Link>
          <Link href="/login" className="rounded-md px-3 py-2 hover:bg-surface-muted">Sign in</Link>
          <Link href="/register" className="rounded-lg bg-primary px-4 py-2 font-medium text-white hover:bg-primary-hover">Get started</Link>
        </nav>
      </header>
      <main>
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-12 md:pt-20">
          <p className="text-sm font-medium text-primary">AI career agent</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight md:text-5xl">
            Find jobs that fit, understand why, and apply with confidence.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-text-muted">
            CareerPilot reads your resume, matches you to relevant roles with transparent explanations, and helps you prepare applications that stay true to your experience.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/register?role=candidate" className="rounded-lg bg-primary px-5 py-3 font-medium text-white hover:bg-primary-hover">I’m looking for a job</Link>
            <Link href="/register?role=employer" className="rounded-lg border border-border-strong bg-surface px-5 py-3 font-medium hover:bg-surface-muted">I’m hiring</Link>
          </div>
        </section>
        <section aria-labelledby="features" className="border-t border-border bg-surface">
          <div className="mx-auto max-w-6xl px-4 py-14">
            <h2 id="features" className="text-xl font-semibold">How it works</h2>
            <ul className="mt-8 grid gap-6 md:grid-cols-2">
              {features.map((f) => (
                <li key={f.title} className="flex gap-4 rounded-xl border border-border p-5">
                  <f.icon className="mt-0.5 h-6 w-6 shrink-0 text-primary" aria-hidden />
                  <div>
                    <h3 className="font-medium">{f.title}</h3>
                    <p className="mt-1 text-sm text-text-muted">{f.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>
      <footer className="mx-auto max-w-6xl px-4 py-8 text-xs text-text-muted">
        CareerPilot AI · Relevance scores are heuristic and are not predictions of hiring outcomes.
      </footer>
    </div>
  );
}
