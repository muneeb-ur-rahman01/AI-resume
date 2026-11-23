"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { AuthCard } from "@/components/auth-card";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { registerSchema, type RegisterValues } from "@/lib/schemas";

function RegisterForm() {
  const params = useSearchParams();
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, control, formState } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { role: params.get("role") === "employer" ? "employer" : "candidate", ai_processing_consent: false, full_name: "", email: "", password: "" },
  });
  const role = useWatch({ control, name: "role" });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      const res = await api<{ message: string }>("/auth/register", { method: "POST", body: values });
      setDone(res.message);
    } catch (e) {
      setError(errorMessage(e));
    }
  });

  if (done) {
    return (
      <AuthCard title="Check your email" footer={<Link className="text-primary underline" href="/login">Back to sign in</Link>}>
        <Alert tone="success">{done}</Alert>
        <p className="mt-4 text-sm text-text-muted">The link expires in 24 hours. In local development, emails appear in Mailpit (http://localhost:8025) or the API log.</p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Create your account" footer={<>Already have an account? <Link className="text-primary underline" href="/login">Sign in</Link></>}>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <fieldset>
          <legend className="mb-2 text-sm font-medium">I want to</legend>
          <div className="grid grid-cols-2 gap-2">
            {(["candidate", "employer"] as const).map((r) => (
              <label key={r} className={`flex cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm ${role === r ? "border-primary bg-primary-soft" : "border-border-strong"}`}>
                <input type="radio" value={r} {...register("role")} />
                {r === "candidate" ? "Find a job" : "Hire talent"}
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="Full name" required error={formState.errors.full_name?.message}>
          {(p) => <Input autoComplete="name" {...p} {...register("full_name")} />}
        </Field>
        <Field label="Email" required error={formState.errors.email?.message} hint={role === "employer" ? "Use your work email; it helps company verification." : undefined}>
          {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
        </Field>
        <Field label="Password" required error={formState.errors.password?.message} hint="At least 12 characters. A passphrase works well.">
          {(p) => <Input type="password" autoComplete="new-password" {...p} {...register("password")} />}
        </Field>
        {role === "candidate" && (
          <label className="flex gap-2 text-sm">
            <input type="checkbox" className="mt-1" {...register("ai_processing_consent")} />
            <span>Allow CareerPilot to process my resume and profile with its configured AI provider to extract information and draft documents. You can change this later; without it, basic non-AI extraction is used.</span>
          </label>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" className="w-full" loading={formState.isSubmitting}>Create account</Button>
      </form>
    </AuthCard>
  );
}

export default function RegisterPage() {
  return <Suspense><RegisterForm /></Suspense>;
}
