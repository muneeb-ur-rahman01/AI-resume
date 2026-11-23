"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";
import { AnyRoleShell } from "@/components/app-shell";
import { Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { Notification, Page } from "@/lib/types";

function List() {
  const qc = useQueryClient();
  const notes = useQuery({ queryKey: ["notifications"], queryFn: () => api<Page<Notification>>("/notifications?page_size=50") });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }) });
  const read = useMutation({ mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }) });
  return (
    <>
      <PageHeader title="Notifications" actions={<Button variant="secondary" size="sm" onClick={() => readAll.mutate()}>Mark all as read</Button>} />
      {notes.isLoading && <LoadingBlock />}
      {notes.isError && <ErrorState error={notes.error} />}
      {notes.data?.items.length === 0 && <EmptyState icon={<Bell className="h-8 w-8" />} title="You're all caught up" />}
      <ul className="space-y-2">
        {notes.data?.items.map((n) => (
          <li key={n.id}>
            <Card className={n.read_at ? "opacity-80" : "border-primary/40"}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{n.title} {!n.read_at && <Badge tone="info">New</Badge>}</p>
                  <p className="mt-1 text-sm text-text-muted">{n.body}</p>
                  <p className="mt-1 text-xs text-text-muted">{dateTime(n.created_at)}</p>
                </div>
                <div className="flex gap-2">
                  {n.link && <Link className="text-sm text-primary underline" href={n.link} onClick={() => read.mutate(n.id)}>Open</Link>}
                  {!n.read_at && <Button size="sm" variant="ghost" onClick={() => read.mutate(n.id)}>Mark read</Button>}
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </>
  );
}

export default function NotificationsPage() {
  return <AnyRoleShell><List /></AnyRoleShell>;
}
