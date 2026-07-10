// Shared fallback-polling helpers for the job-status `useQuery` hooks in
// `project-dashboard.tsx`. These replace the five independent recursive
// `setTimeout` loops described in docs/ui/frontend-architecture.md
// ("Root-Cause Analysis" #2 and "Fallback polling with backoff"): every job
// poll now goes through TanStack Query's `refetchInterval`, backing off
// exponentially while a job's status is unchanged and stopping outright once
// the job reaches a terminal status.

export type JobLikeStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | string;

const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);

export function isActiveJobStatus(status: JobLikeStatus | null | undefined): boolean {
  return status != null && ACTIVE_JOB_STATUSES.has(status);
}

/**
 * Returns a stateful backoff function (hold it in a `useRef` so its streak
 * survives re-renders): each call reports the next poll interval given the
 * latest observed status. The interval doubles, capped at `capMs`, for every
 * consecutive *fetch* that reports the same status; it resets to `baseMs`
 * the moment the status changes (queued -> running, etc.), so a job that is
 * actively progressing keeps polling promptly while one that's stuck
 * gradually backs off.
 *
 * Must be called with TanStack Query's `query.state.dataUpdateCount` as the
 * second argument, not just the latest status. `refetchInterval` callbacks
 * are re-evaluated on effectively every render of the observing component
 * (not only after a real fetch resolves — `useQuery` calls
 * `observer.setOptions` on every render, which recomputes the interval), so
 * a naive "call count" backoff would advance its streak dozens of times
 * between two actual network requests and balloon the interval almost
 * immediately. Keying off `dataUpdateCount` — which only increments once
 * per completed fetch — makes repeated same-tick calls idempotent.
 */
export function createPollBackoff(baseMs: number, capMs = 15_000) {
  let lastDataUpdateCount = -1;
  let lastStatus: JobLikeStatus | undefined;
  let streak = 0;
  let lastInterval = baseMs;
  return (status: JobLikeStatus | null | undefined, dataUpdateCount: number): number => {
    if (dataUpdateCount === lastDataUpdateCount) return lastInterval;
    lastDataUpdateCount = dataUpdateCount;
    const normalized = status ?? undefined;
    if (normalized !== undefined && normalized === lastStatus) {
      streak += 1;
    } else {
      streak = 0;
      lastStatus = normalized;
    }
    lastInterval = Math.min(baseMs * 2 ** streak, capMs);
    return lastInterval;
  };
}
