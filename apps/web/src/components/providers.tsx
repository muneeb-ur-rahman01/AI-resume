"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; message: string; tone: "success" | "danger" | "info" };
const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});
export const useToast = () => useContext(ToastContext);

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            refetchOnWindowFocus: false,
            retry: (count, err) => count < 2 && ![401, 403, 404].includes((err as { status?: number }).status ?? 0),
          },
        },
      }),
  );
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, tone: Toast["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <QueryClientProvider client={client}>
      <ToastContext.Provider value={push}>
        {children}
        <div aria-live="polite" role="status" className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={
                "rounded-lg border px-4 py-3 text-sm shadow-md " +
                (t.tone === "danger" ? "border-danger/30 bg-danger-soft text-danger" : t.tone === "info" ? "border-info/30 bg-info-soft" : "border-success/30 bg-success-soft")
              }
            >
              {t.message}
            </div>
          ))}
        </div>
      </ToastContext.Provider>
    </QueryClientProvider>
  );
}
