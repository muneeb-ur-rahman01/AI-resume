"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { AuthCard } from "@/components/auth-card";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { homeFor } from "@/lib/hooks";
import { loginSchema, type LoginValues } from "@/lib/schemas";
import type { Me } from "@/lib/types";

function safeNext(next: string | null): string | null {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [error, setError] = useState<{ message: string; unverified?: boolean } | null>(null);
  const [resent, setResent] = useState(false);
  const { register, handleSubmit, formState, getValues } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      const me = await api<Me>("/auth/login", { method: "POST", body: values });
      qc.setQueryData(["me"], me);
      router.replace(safeNext(params.get("next")) ?? homeFor(me.roles));
    } catch (e) {
      setError({ message: errorMessage(e), unverified: e instanceof ApiError && e.code === "email_not_verified" });
    }
  });

  async function resend() {
    await api("/auth/resend-verification", { method: "POST", body: { email: getValues("email") } }).catch(() => {});
    setResent(true);
  }

  return (
    <AuthCard title="Sign in" footer={<>New here? <Link className="text-primary underline" href="/register">Create an account</Link></>}>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Field label="Email" required error={formState.errors.email?.message}>
          {(p) => <Input type="email" autoComplete="email" {...p} {...register("email")} />}
        </Field>
        <Field label="Password" required error={formState.errors.password?.message}>
          {(p) => <Input type="password" autoComplete="current-password" {...p} {...register("password")} />}
        </Field>
        {error && (
          <Alert tone="danger">
            {error.message}
            {error.unverified && !resent && <button type="button" onClick={resend} className="ml-1 text-primary underline">Resend verification email</button>}
            {resent && <span className="ml-1">If the account is unverified, a new link was sent.</span>}
          </Alert>
        )}
        <Button type="submit" className="w-full" loading={formState.isSubmitting}>Sign in</Button>
        <p className="text-center text-sm"><Link className="text-primary underline" href="/forgot-password">Forgot your password?</Link></p>
      </form>
    </AuthCard>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
