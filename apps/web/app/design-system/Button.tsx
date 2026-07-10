"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./primitives.module.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive" | "icon";
export type ButtonSize = "sm" | "md" | "lg";

export function Button({ variant = "primary", size = "md", leadingIcon, trailingIcon, className, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize; leadingIcon?: ReactNode; trailingIcon?: ReactNode }) {
  return <button {...props} className={[styles.button, styles[variant], styles[size], variant === "icon" ? styles.icon : "", className].filter(Boolean).join(" ")}>
    {leadingIcon}<span>{children}</span>{trailingIcon}
  </button>;
}
