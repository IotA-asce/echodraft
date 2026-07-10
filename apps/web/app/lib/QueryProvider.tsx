"use client";

import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./query-client";

// Thin client-boundary wrapper so the (server) RootLayout can mount the
// TanStack Query cache without itself needing "use client". See
// docs/ui/frontend-architecture.md ("Server cache: TanStack Query").
export function QueryProvider({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
