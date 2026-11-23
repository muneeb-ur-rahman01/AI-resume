import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CareerPilot AI", template: "%s · CareerPilot AI" },
  description: "Find relevant jobs, understand why they match, and apply with documents you approve.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-text">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
