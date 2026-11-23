"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AuthCard } from "@/components/auth-card";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { resetSchema } from "@/lib/schemas";

function Reset() {
  const token = useSearchParams().get("token");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const { register, handleSubmit, formState } = useForm<z.infer<typeof resetSchema>>({ resolver: zodResolver(resetSchema) });
  const onSubmit = handleSubmit(async (v) => {
    try {
      const r = await api<{ message: string }>("/auth/reset-password", { method: "POST", body: { token, new_password: v.password } });
      setMsg({ ok: true, text: r.message });
    } catch (e) {
      setMsg({ ok: false, text: errorMessage(e) });
    }
  });
  if (!token) return <AuthCard title="Reset password"><Alert tone="danger">This link is missing its token.</Alert></AuthCard>;
  return (
    <AuthCard title="Choose a new password" footer={<Link className="text-primary underline" href="/login">Back to sign in</Link>}>
      {msg?.ok ? <Alert tone="success">{msg.text}</Alert> : (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field label="New password" required error={formState.errors.password?.message}>{(p) => <Input type="password" autoComplete="new-password" {...p} {...register("password")} />}</Field>
          <Field label="Confirm password" required error={formState.errors.confirm?.message}>{(p) => <Input type="password" autoComplete="new-password" {...p} {...register("confirm")} />}</Field>
          {msg && <Alert tone="danger">{msg.text}</Alert>}
          <Button type="submit" className="w-full" loading={formState.isSubmitting}>Reset password</Button>
        </form>
      )}
    </AuthCard>
  );
}

export default function ResetPasswordPage() {
  return <Suspense><Reset /></Suspense>;
}
