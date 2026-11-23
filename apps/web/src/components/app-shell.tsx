"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Briefcase, Building2, FileText, LayoutDashboard, LogOut, Search, Settings, Shield, Sparkles, User } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/hooks";
import type { Page, Notification } from "@/lib/types";
import { Alert, cn, LoadingBlock } from "./ui";

const NAV = {
  candidate: [
    { href: "/candidate", label: "Dashboard", icon: LayoutDashboard },
    { href: "/candidate/recommendations", label: "Recommended jobs", icon: Sparkles },
    { href: "/jobs", label: "Search jobs", icon: Search },
    { href: "/candidate/resumes", label: "Resumes", icon: FileText },
    { href: "/candidate/profile", label: "Profile", icon: User },
    { href: "/candidate/applications", label: "Applications", icon: Briefcase },
  ],
  employer: [
    { href: "/employer", label: "Dashboard", icon: LayoutDashboard },
    { href: "/employer/company", label: "Company", icon: Building2 },
    { href: "/employer/jobs/new", label: "Post a job", icon: Briefcase },
  ],
  admin: [{ href: "/admin", label: "Admin console", icon: Shield }],
} as const;

export function AppShell({ role, children }: { role: keyof typeof NAV; children: ReactNode }) {
  const { me, allowed, forbidden } = useRequireRole(role);
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api<Page<Notification>>("/notifications?unread_only=true&page_size=1"),
    enabled: allowed,
    refetchInterval: 60_000,
  });

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      qc.clear();
      router.replace("/login");
    }
  }

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only-focusable fixed left-2 top-2 z-50 rounded bg-surface px-3 py-2 shadow">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
          <Link href="/" className="font-semibold tracking-tight">CareerPilot<span className="text-primary"> AI</span></Link>
          <nav aria-label="Primary" className="hidden flex-1 gap-1 overflow-x-auto md:flex">
            {NAV[role].map((item) => {
              const active = pathname === item.href || (item.href !== `/${role}` && pathname.startsWith(item.href));
              return (
                <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}
                  className={cn("flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-sm", active ? "bg-primary-soft text-primary" : "text-text-muted hover:bg-surface-muted")}>
                  <item.icon className="h-4 w-4" aria-hidden /> {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <Link href="/notifications" className="relative rounded-md p-2 hover:bg-surface-muted" aria-label={`Notifications${unread.data?.total ? `, ${unread.data.total} unread` : ""}`}>
              <Bell className="h-5 w-5" aria-hidden />
              {!!unread.data?.total && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-danger" aria-hidden />}
            </Link>
            <Link href="/settings" className="rounded-md p-2 hover:bg-surface-muted" aria-label="Settings"><Settings className="h-5 w-5" aria-hidden /></Link>
            <button onClick={logout} className="rounded-md p-2 hover:bg-surface-muted" aria-label="Sign out"><LogOut className="h-5 w-5" aria-hidden /></button>
          </div>
        </div>
        <nav aria-label="Primary mobile" className="flex gap-1 overflow-x-auto border-t border-border px-2 py-1 md:hidden">
          {NAV[role].map((item) => (
            <Link key={item.href} href={item.href} className={cn("whitespace-nowrap rounded-md px-3 py-1.5 text-xs", pathname === item.href ? "bg-primary-soft text-primary" : "text-text-muted")}>{item.label}</Link>
          ))}
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-8">
        {me.isLoading || (!me.data && !me.isError) ? <LoadingBlock /> : null}
        {me.isError && <Alert tone="danger" title="We couldn't verify your session">Please refresh the page.</Alert>}
        {forbidden && <Alert tone="warning" title="You don't have access to this area">This section is for {role} accounts.</Alert>}
        {allowed && children}
      </main>
    </div>
  );
}

/** Shell for pages any signed-in role can use (settings, notifications). */
export function AnyRoleShell({ children }: { children: ReactNode }) {
  const { me } = useRequireRole("candidate");
  const roles = me.data?.roles ?? [];
  const role = roles.includes("admin") ? "admin" : roles.includes("employer") ? "employer" : "candidate";
  if (!me.data) return <main className="mx-auto max-w-3xl px-4 py-8"><LoadingBlock /></main>;
  return <AppShell role={role}>{children}</AppShell>;
}
