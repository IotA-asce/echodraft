import type { ReactNode } from "react";

export function StatusBadge({ status, children }: { status: string; children: ReactNode }) {
  return <span className={`status-badge ${status}`}>{children}</span>;
}
