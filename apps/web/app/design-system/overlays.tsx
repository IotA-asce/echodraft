"use client";

import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import styles from "./primitives.module.css";

type OverlayProps = { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: ReactNode; footer?: ReactNode; size?: "sm" | "md" | "lg" };

function useOverlay(open: boolean, onOpenChange: (open: boolean) => void) {
  const panel = useRef<HTMLDivElement>(null);
  const restore = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) return;
    restore.current = document.activeElement as HTMLElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    queueMicrotask(() => panel.current?.querySelector<HTMLElement>("button, [href], input, [tabindex]:not([tabindex='-1'])")?.focus());
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onOpenChange(false); return; }
      if (event.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>("button:not(:disabled), [href], input:not(:disabled), [tabindex]:not([tabindex='-1'])")];
      const first = items[0], last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); document.body.style.overflow = previousOverflow; restore.current?.focus(); };
  }, [open, onOpenChange]);
  return panel;
}

export function Modal(props: OverlayProps) { return <Overlay {...props} kind="modal" />; }
export function Drawer(props: Omit<OverlayProps, "size">) { return <Overlay {...props} kind="drawer" />; }

function Overlay({ open, onOpenChange, title, description, children, footer, size = "md", kind }: OverlayProps & { kind: "modal" | "drawer" }) {
  const titleId = useId(), descriptionId = useId();
  const panel = useOverlay(open, onOpenChange);
  if (!open || typeof document === "undefined") return null;
  const modalClass = size === "sm" ? styles.modalSm : size === "lg" ? styles.modalLg : "";
  return createPortal(<div className={[styles.backdrop, kind === "drawer" ? styles.drawerBackdrop : ""].filter(Boolean).join(" ")} onMouseDown={(event) => { if (event.target === event.currentTarget) onOpenChange(false); }}>
    <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined} className={kind === "drawer" ? styles.drawer : [styles.modal, modalClass].filter(Boolean).join(" ")}>
      <h2 id={titleId} className={styles.overlayTitle}>{title}</h2>
      {description ? <p id={descriptionId} className={styles.overlayDescription}>{description}</p> : null}
      <div className={styles.overlayBody}>{children}</div>
      {footer ? <footer className={styles.overlayFooter}>{footer}</footer> : null}
    </div>
  </div>, document.body);
}

type Toast = { id: string; message: string; persistent: boolean };
const ToastContext = createContext<((message: string, options?: { persistent?: boolean }) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: string) => setToasts((current) => current.filter((toast) => toast.id !== id)), []);
  const push = useCallback((message: string, options?: { persistent?: boolean }) => {
    const id = crypto.randomUUID();
    const persistent = options?.persistent ?? false;
    setToasts((current) => [...current, { id, message, persistent }].slice(-3));
    if (!persistent) window.setTimeout(() => dismiss(id), 4000);
  }, [dismiss]);
  return <ToastContext.Provider value={push}>{children}<div className={styles.toastViewport} aria-live="polite" aria-label="Notifications">{toasts.map((toast) => <div className={styles.toast} key={toast.id}><span>{toast.message}</span><button type="button" className={styles.toastClose} aria-label="Dismiss notification" onClick={() => dismiss(toast.id)}>×</button></div>)}</div></ToastContext.Provider>;
}

export function useToast() { const value = useContext(ToastContext); if (!value) throw new Error("useToast must be used within ToastProvider"); return value; }
