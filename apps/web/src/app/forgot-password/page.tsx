"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AuthCard } from "@/components/auth-card";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [loading, setLoading] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const r = await api<{ message: string }>("/auth/forgot-password", { method: "POST", body: { email } });
      setMsg({ ok: true, text: r.message });
    } catch (err) {
      setMsg({ ok: false, text: errorMessage(err) });
    } finally {
      setLoading(false);
    }
  }
  return (
    <AuthCard title="Reset your password" subtitle="We'll email you a link that works once and expires in 30 minutes." footer={<Link className="text-primary underline" href="/login">Back to sign in</Link>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email" required>{(p) => <Input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} {...p} />}</Field>
        {msg && <Alert tone={msg.ok ? "success" : "danger"}>{msg.text}</Alert>}
        <Button type="submit" className="w-full" loading={loading}>Send reset link</Button>
      </form>
    </AuthCard>
  );
}
