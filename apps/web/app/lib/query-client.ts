import { QueryClient } from "@tanstack/react-query";

// Singleton TanStack Query cache for the whole app (mounted once in
// `app/layout.tsx`). See docs/ui/frontend-architecture.md ("State & Data
// Layer" -> "Server cache: TanStack Query") for the rationale: this is the
// server-state cache the job-poll hooks and future feature hooks read from,
// replacing the recursive `setTimeout` poll loops that used to live directly
// on `ProjectDashboard`'s top-level state.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Job/poll-shaped queries opt into their own `refetchInterval`; general
      // structural data (chapters, characters, ...) is fetched imperatively
      // today and will move onto this client incrementally (see migration
      // plan in frontend-architecture.md), so a conservative default keeps
      // any newly-added query from refetching more than necessary.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
