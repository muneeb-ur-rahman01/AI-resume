"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Company } from "./types";

export function useMyCompany() {
  const q = useQuery({ queryKey: ["my-companies"], queryFn: () => api<Company[]>("/employer/companies") });
  return { ...q, company: q.data?.[0] ?? null };
}
