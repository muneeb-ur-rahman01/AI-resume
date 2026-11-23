"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api, ApiError } from "./api";
import type { Me } from "./types";

export function useMe() {
  return useQuery<Me | null>({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
  });
}

/** Client-side guard for UX only. Authorization is enforced by the API on every request. */
export function useRequireRole(role: "candidate" | "employer" | "admin") {
  const me = useMe();
  const router = useRouter();
  useEffect(() => {
    if (me.isSuccess && !me.data) {
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  }, [me.isSuccess, me.data, router]);
  const allowed = !!me.data?.roles.includes(role);
  return { me, allowed, forbidden: !!me.data && !allowed };
}

export function homeFor(roles: string[]): string {
  if (roles.includes("admin")) return "/admin";
  if (roles.includes("employer")) return "/employer";
  return "/candidate";
}
