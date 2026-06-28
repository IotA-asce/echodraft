import type { ReactNode } from "react";

export function InlineNotice({ tone, children }: { tone: "success" | "error" | "info"; children: ReactNode }) {
  return (
    <p className={`notice inline-notice ${tone}`} role={tone === "error" ? "alert" : undefined} aria-live={tone === "error" ? undefined : "polite"}>
      {children}
    </p>
  );
}
