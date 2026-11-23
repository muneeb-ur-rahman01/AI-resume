"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { Alert, LoadingBlock } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<{ ok: boolean; message: string } | null>(null);
  const sent = useRef(false);
  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true; // the token is single-use; never submit twice (e.g. React strict mode)
    api<{ message: string }>("/auth/verify-email", { method: "POST", body: { token } })
      .then((r) => setState({ ok: true, message: r.message }))
      .catch((e) => setState({ ok: false, message: errorMessage(e) }));
  }, [token]);
  return (
    <AuthCard title="Email verification" footer={<Link className="text-primary underline" href="/login">Go to sign in</Link>}>
      {!token && <Alert tone="danger">This link is missing its token. Open the link from your email again.</Alert>}
      {token && !state && <LoadingBlock label="Verifying" />}
      {state && <Alert tone={state.ok ? "success" : "danger"}>{state.message}</Alert>}
    </AuthCard>
  );
}

export default function VerifyEmailPage() {
  return <Suspense><Verify /></Suspense>;
}
