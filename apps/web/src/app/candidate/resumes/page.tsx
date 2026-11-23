"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { useToast } from "@/components/providers";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, LoadingBlock, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { date, label, STATUS_TONE } from "@/lib/format";
import type { Resume } from "@/lib/types";

const MAX_MB = 10;

export default function ResumesPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [toDelete, setToDelete] = useState<Resume | null>(null);
  const resumes = useQuery({
    queryKey: ["resumes"],
    queryFn: () => api<Resume[]>("/candidate/resumes"),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "queued" || r.status === "processing") ? 3000 : false),
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api<Resume>("/candidate/resumes", { method: "POST", formData: fd });
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["resumes"] });
      toast(r.status === "completed" ? "Resume processed. Review the extracted details." : "Resume uploaded. Processing has started.");
    },
    onError: (e) => setError(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/candidate/resumes/${id}`, { method: "DELETE" }),
    onSuccess: () => { setToDelete(null); qc.invalidateQueries({ queryKey: ["resumes"] }); toast("Resume deleted."); },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  function pick(file: File | undefined) {
    setError(null);
    if (!file) return;
    if (!/\.(pdf|docx)$/i.test(file.name)) return setError("Only PDF and DOCX files are supported.");
    if (file.size > MAX_MB * 1024 * 1024) return setError(`The file exceeds the ${MAX_MB} MB limit.`);
    upload.mutate(file);
  }

  return (
    <>
      <PageHeader title="Resumes" description="Upload a resume to extract your skills and experience. Nothing is added to your profile until you confirm it." />
      <Card>
        <div
          onDragOver={(e: DragEvent) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e: DragEvent) => { e.preventDefault(); setDragging(false); pick(e.dataTransfer.files[0]); }}
          className={`flex flex-col items-center rounded-lg border-2 border-dashed px-6 py-10 text-center ${dragging ? "border-primary bg-primary-soft" : "border-border-strong"}`}
        >
          <Upload className="h-8 w-8 text-text-muted" aria-hidden />
          <p className="mt-3 font-medium">Drag and drop your resume here</p>
          <p className="text-sm text-text-muted">PDF or DOCX, up to {MAX_MB} MB. Password-protected and macro-enabled files are rejected.</p>
          <input ref={inputRef} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="sr-only" id="resume-file"
            onChange={(e: ChangeEvent<HTMLInputElement>) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
          <Button className="mt-4" loading={upload.isPending} onClick={() => inputRef.current?.click()}>Choose file</Button>
        </div>
        {error && <Alert tone="danger" className="mt-4">{error}</Alert>}
      </Card>

      <div className="mt-6 space-y-3">
        {resumes.isLoading && <LoadingBlock />}
        {resumes.isError && <ErrorState error={resumes.error} onRetry={() => resumes.refetch()} />}
        {resumes.data?.length === 0 && <EmptyState icon={<FileText className="h-8 w-8" />} title="No resumes yet" description="Your uploaded resumes will appear here." />}
        {resumes.data?.map((r) => (
          <Card key={r.id} className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-medium">{r.label} {r.is_primary && <Badge tone="info">Primary</Badge>}</p>
              <p className="text-sm text-text-muted">{r.filename} · {(r.size_bytes / 1024).toFixed(0)} KB · uploaded {date(r.created_at)}</p>
              {r.status_detail && <p className="mt-1 text-sm text-text-muted">{r.status_detail}</p>}
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={STATUS_TONE[r.status]}>{label(r.status)}</Badge>
              {r.status === "completed" && <Link className="text-sm text-primary underline" href={`/candidate/resumes/${r.id}`}>Review details</Link>}
              <a className="text-sm text-primary underline" href={`/api/v1/candidate/resumes/${r.id}/download`}>Download</a>
              <Button variant="ghost" size="sm" onClick={() => setToDelete(r)} aria-label={`Delete ${r.label}`}>Delete</Button>
            </div>
          </Card>
        ))}
      </div>
      <ConfirmDialog open={!!toDelete} title="Delete this resume?" tone="danger" confirmLabel="Delete"
        description="The file and its extracted data will be permanently deleted. Applications you already submitted keep their snapshot."
        loading={remove.isPending} onClose={() => setToDelete(null)} onConfirm={() => toDelete && remove.mutate(toDelete.id)} />
    </>
  );
}
