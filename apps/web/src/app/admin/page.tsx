"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useToast } from "@/components/providers";
import { Badge, Button, Card, ErrorState, Field, Input, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dateTime, label, STATUS_TONE } from "@/lib/format";
import type { Company, Page, Verification } from "@/lib/types";

type Metrics = { users: number; published_jobs: number; failed_tasks: number; open_reports: number; pending_verifications: number; ai_usage: { operation: string; success: boolean; calls: number; estimated_cost_usd: number; avg_latency_ms: number }[] };
type PendingCompany = { company: Company; latest_request: Verification | null };
type Report = { id: string; target_type: string; target_id: string; reason: string; details: string | null; created_at: string };
type Task = { id: string; name: string; entity_id: string | null; attempts: number; last_error: string | null; created_at: string };
type AuditRow = { id: string; actor_user_id: string | null; action: string; target_type: string | null; target_id: string | null; created_at: string; request_id: string | null };
type AdminUser = { id: string; email: string; full_name: string; roles: string[]; status: string; email_verified: boolean; created_at: string };

function Stat({ label: l, value }: { label: string; value: number | string }) {
  return <Card className="p-4"><p className="text-xs text-text-muted">{l}</p><p className="mt-1 text-2xl font-semibold">{value}</p></Card>;
}

function Verifications() {
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ["admin-companies"], queryFn: () => api<PendingCompany[]>("/admin/companies?status=pending") });
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) => api(`/admin/companies/${id}/verification`, { method: "POST", body: { approve, reason: approve ? null : "Insufficient evidence" } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-companies"] }); qc.invalidateQueries({ queryKey: ["admin-metrics"] }); toast("Decision recorded."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  return (
    <Card>
      <h2 className="font-semibold">Employer verification queue</h2>
      {list.isLoading && <LoadingBlock />}
      {list.data?.length === 0 && <p className="mt-2 text-sm text-text-muted">No pending requests.</p>}
      <ul className="mt-3 divide-y divide-border">
        {list.data?.map(({ company, latest_request: r }) => (
          <li key={company.id} className="py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">{company.name} <span className="text-text-muted">· {company.email_domain ?? "no domain"} · {company.website ?? "no website"}</span></p>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => decide.mutate({ id: company.id, approve: true })}>Approve</Button>
                <Button size="sm" variant="danger" onClick={() => decide.mutate({ id: company.id, approve: false })}>Reject</Button>
              </div>
            </div>
            {r && (
              <div className="mt-2 text-xs text-text-muted">
                <p>Signals: {Object.entries(r.signals).map(([k, v]) => `${label(k)}: ${String(v)}`).join(" · ")}</p>
                {r.evidence_note && <p>Note: {r.evidence_note}</p>}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Reports() {
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({ queryKey: ["admin-reports"], queryFn: () => api<Report[]>("/admin/reports") });
  const resolve = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => api(`/admin/reports/${id}/resolve`, { method: "POST", body: { action, reason: `Admin action: ${action}` } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-reports"] }); toast("Report resolved."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  return (
    <Card>
      <h2 className="font-semibold">Open abuse reports</h2>
      {list.data?.length === 0 && <p className="mt-2 text-sm text-text-muted">No open reports.</p>}
      <ul className="mt-3 divide-y divide-border text-sm">
        {list.data?.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
            <span><Badge tone="warning">{label(r.reason)}</Badge> {r.target_type} <a className="text-primary underline" href={`/jobs/${r.target_id}`}>{r.target_id.slice(0, 8)}</a> · {dateTime(r.created_at)}{r.details && <span className="block text-text-muted">{r.details}</span>}</span>
            <span className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => resolve.mutate({ id: r.id, action: "dismiss" })}>Dismiss</Button>
              <Button size="sm" variant="secondary" onClick={() => resolve.mutate({ id: r.id, action: "pause_job" })}>Pause job</Button>
              <Button size="sm" variant="danger" onClick={() => resolve.mutate({ id: r.id, action: "close_job" })}>Close job</Button>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Tasks() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["admin-tasks"], queryFn: () => api<Task[]>("/admin/tasks?status=failed") });
  const retry = useMutation({ mutationFn: (id: string) => api(`/admin/tasks/${id}/retry`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-tasks"] }) });
  return (
    <Card>
      <h2 className="font-semibold">Failed background tasks</h2>
      {list.data?.length === 0 && <p className="mt-2 text-sm text-text-muted">No failed tasks.</p>}
      <ul className="mt-3 divide-y divide-border text-sm">
        {list.data?.map((t) => (
          <li key={t.id} className="flex items-center justify-between gap-2 py-2">
            <span>{t.name} · {t.entity_id?.slice(0, 8)} · {t.attempts} attempt(s) · {t.last_error ?? "unknown error"}</span>
            <Button size="sm" variant="secondary" onClick={() => retry.mutate(t.id)}>Retry</Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Users() {
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["admin-users", q], queryFn: () => api<Page<AdminUser>>(`/admin/users?page_size=25${q ? `&q=${encodeURIComponent(q)}` : ""}`) });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "suspend" | "reinstate" }) => api(`/admin/users/${id}/${action}`, { method: "POST", body: { reason: `Admin ${action} from console` } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-users"] }); toast("User updated."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  return (
    <Card>
      <h2 className="font-semibold">Users</h2>
      <div className="mt-3 max-w-sm"><Field label="Search by email or name">{(a) => <Input {...a} value={q} onChange={(e) => setQ(e.target.value)} />}</Field></div>
      <ul className="mt-3 divide-y divide-border text-sm">
        {list.data?.items.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>{u.full_name} · {u.email} · {u.roles.join(", ")} <Badge tone={STATUS_TONE[u.status] ?? (u.status === "active" ? "success" : "neutral")}>{label(u.status)}</Badge></span>
            {!u.roles.includes("admin") && (u.status === "active"
              ? <Button size="sm" variant="danger" onClick={() => act.mutate({ id: u.id, action: "suspend" })}>Suspend</Button>
              : u.status === "suspended" && <Button size="sm" variant="secondary" onClick={() => act.mutate({ id: u.id, action: "reinstate" })}>Reinstate</Button>)}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Audit() {
  const [action, setAction] = useState("");
  const list = useQuery({ queryKey: ["admin-audit", action], queryFn: () => api<Page<AuditRow>>(`/admin/audit-events?page_size=50${action ? `&action=${encodeURIComponent(action)}` : ""}`) });
  return (
    <Card className="overflow-x-auto">
      <h2 className="font-semibold">Audit log</h2>
      <div className="mt-3 max-w-sm"><Field label="Filter by action prefix" hint="e.g. admin. or auth.login">{(a) => <Input {...a} value={action} onChange={(e) => setAction(e.target.value)} />}</Field></div>
      <table className="mt-3 w-full text-left text-xs">
        <caption className="sr-only">Audit events</caption>
        <thead className="text-text-muted"><tr><th className="py-1">Time</th><th>Action</th><th>Actor</th><th>Target</th><th>Request</th></tr></thead>
        <tbody>{list.data?.items.map((e) => <tr key={e.id} className="border-t border-border"><td className="py-1">{dateTime(e.created_at)}</td><td>{e.action}</td><td>{e.actor_user_id?.slice(0, 8) ?? "system"}</td><td>{e.target_type} {e.target_id?.slice(0, 8)}</td><td>{e.request_id?.slice(0, 8)}</td></tr>)}</tbody>
      </table>
    </Card>
  );
}

function Console() {
  const metrics = useQuery({ queryKey: ["admin-metrics"], queryFn: () => api<Metrics>("/admin/metrics") });
  return (
    <>
      <PageHeader title="Admin console" description="All actions here are recorded in the audit log." />
      {metrics.isError && <ErrorState error={metrics.error} />}
      {metrics.data && (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Users" value={metrics.data.users} /><Stat label="Published jobs" value={metrics.data.published_jobs} />
          <Stat label="Pending verifications" value={metrics.data.pending_verifications} /><Stat label="Open reports" value={metrics.data.open_reports} />
          <Stat label="Failed tasks" value={metrics.data.failed_tasks} />
        </div>
      )}
      {metrics.data && metrics.data.ai_usage.length > 0 && (
        <Card className="mb-6">
          <h2 className="font-semibold">AI usage (last 7 days)</h2>
          <ul className="mt-2 text-sm">{metrics.data.ai_usage.map((u) => <li key={u.operation + u.success}>{u.operation} · {u.success ? "ok" : "failed"} · {u.calls} call(s) · ~${u.estimated_cost_usd} · {u.avg_latency_ms} ms avg</li>)}</ul>
        </Card>
      )}
      <div className="space-y-6"><Verifications /><Reports /><Tasks /><Users /><Audit /></div>
    </>
  );
}

export default function AdminPage() {
  return <AppShell role="admin"><Console /></AppShell>;
}
