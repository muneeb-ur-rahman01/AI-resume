"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AnyRoleShell } from "@/components/app-shell";
import { useToast } from "@/components/providers";
import { Alert, Badge, Button, Card, ConfirmDialog, Field, Input, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { SessionInfo } from "@/lib/types";

type Consents = { ai_processing: boolean; recommendation_tracking: boolean };
type Prefs = { email_application_updates: boolean; email_recommendations: boolean; email_processing_updates: boolean };

function PrivacyCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const consents = useQuery({ queryKey: ["consents"], queryFn: () => api<Consents>("/privacy/consents") });
  const save = useMutation({
    mutationFn: (c: Consents) => api<Consents>("/privacy/consents", { method: "PUT", body: c }),
    onSuccess: (c) => { qc.setQueryData(["consents"], c); toast("Privacy settings saved."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  if (!consents.data) return <LoadingBlock />;
  const c = consents.data;
  return (
    <Card>
      <h2 className="font-semibold">Privacy & AI consent</h2>
      <div className="mt-4 space-y-4 text-sm">
        <label className="flex gap-3"><input type="checkbox" className="mt-1" checked={c.ai_processing} onChange={(e) => save.mutate({ ...c, ai_processing: e.target.checked })} />
          <span><span className="font-medium">AI processing.</span> Send my resume text and confirmed profile to the configured AI provider for extraction and drafting. Without it, basic non-AI extraction is used and drafting is disabled.</span></label>
        <label className="flex gap-3"><input type="checkbox" className="mt-1" checked={c.recommendation_tracking} onChange={(e) => save.mutate({ ...c, recommendation_tracking: e.target.checked })} />
          <span><span className="font-medium">Recommendation feedback.</span> Record which recommendations I view, save or apply to, used only for offline evaluation of matching quality.</span></label>
      </div>
    </Card>
  );
}

function NotificationsCard() {
  const qc = useQueryClient();
  const prefs = useQuery({ queryKey: ["notif-prefs"], queryFn: () => api<Prefs>("/notifications/preferences") });
  const save = useMutation({ mutationFn: (p: Prefs) => api<Prefs>("/notifications/preferences", { method: "PUT", body: p }), onSuccess: (p) => qc.setQueryData(["notif-prefs"], p) });
  if (!prefs.data) return <LoadingBlock />;
  const p = prefs.data;
  const row = (k: keyof Prefs, text: string) => (
    <label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={p[k]} onChange={(e) => save.mutate({ ...p, [k]: e.target.checked })} />{text}</label>
  );
  return (
    <Card>
      <h2 className="font-semibold">Email notifications</h2>
      <div className="mt-4 space-y-3">{row("email_application_updates", "Application updates")}{row("email_processing_updates", "Resume processing results")}{row("email_recommendations", "New job recommendations")}</div>
      <p className="mt-3 text-xs text-text-muted">Security emails (password changes, verification) are always sent.</p>
    </Card>
  );
}

function SecurityCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionInfo[]>("/auth/sessions") });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const change = useMutation({
    mutationFn: () => api("/auth/change-password", { method: "POST", body: pw }),
    onSuccess: () => { setPw({ current_password: "", new_password: "" }); toast("Password changed. Other sessions were signed out."); qc.invalidateQueries({ queryKey: ["sessions"] }); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api(`/auth/sessions/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }) });
  const revokeOthers = useMutation({ mutationFn: () => api("/auth/sessions/revoke-others", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }) });
  return (
    <Card>
      <h2 className="font-semibold">Security</h2>
      <form className="mt-4 grid gap-3 md:grid-cols-3" onSubmit={(e) => { e.preventDefault(); change.mutate(); }}>
        <Field label="Current password">{(a) => <Input {...a} type="password" autoComplete="current-password" required value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />}</Field>
        <Field label="New password" hint="12+ characters">{(a) => <Input {...a} type="password" autoComplete="new-password" required value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />}</Field>
        <div className="flex items-end"><Button type="submit" loading={change.isPending}>Change password</Button></div>
      </form>
      <h3 className="mt-6 text-sm font-medium">Active sessions</h3>
      <ul className="mt-2 divide-y divide-border text-sm">
        {sessions.data?.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="min-w-0 truncate">{s.user_agent ?? "Unknown device"} · {s.ip_prefix ?? "unknown network"} · last active {dateTime(s.last_seen_at)}</span>
            {s.current ? <Badge tone="info">This device</Badge> : <Button size="sm" variant="ghost" onClick={() => revoke.mutate(s.id)}>Sign out</Button>}
          </li>
        ))}
      </ul>
      <Button variant="secondary" size="sm" className="mt-3" onClick={() => revokeOthers.mutate()} loading={revokeOthers.isPending}>Sign out all other sessions</Button>
    </Card>
  );
}

function DataCard() {
  const router = useRouter();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: () => api("/privacy/delete-account", { method: "POST", body: { password } }),
    onSuccess: () => { qc.clear(); router.replace("/?deleted=1"); },
    onError: (e) => setError(errorMessage(e)),
  });
  async function exportData() {
    const data = await api<object>("/privacy/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = "careerpilot-export.json"; a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <Card>
      <h2 className="font-semibold">Your data</h2>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="secondary" onClick={exportData}>Download my data (JSON)</Button>
        <Button variant="danger" onClick={() => setOpen(true)}>Delete my account</Button>
      </div>
      <ConfirmDialog open={open} title="Permanently delete your account?" tone="danger" confirmLabel="Delete account" loading={remove.isPending}
        description="Your profile, resumes, drafts and applications will be deleted. This cannot be undone." onClose={() => setOpen(false)} onConfirm={() => remove.mutate()}>
        <Field label="Confirm with your password">{(a) => <Input {...a} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
        {error && <Alert tone="danger" className="mt-2">{error}</Alert>}
      </ConfirmDialog>
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <AnyRoleShell>
      <PageHeader title="Settings" description="Privacy, notifications, security and your data." />
      <div className="space-y-6"><PrivacyCard /><NotificationsCard /><SecurityCard /><DataCard /></div>
    </AnyRoleShell>
  );
}
