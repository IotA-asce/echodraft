"use client";

import type { CSSProperties } from "react";
import styles from "./primitives.module.css";

export function Range({ label, value, min, max, step = 1, onValueChange, formatValue = String, disabled = false, className }: { label: string; value: number; min: number; max: number; step?: number; onValueChange: (value: number) => void; formatValue?: (value: number) => string; disabled?: boolean; className?: string }) {
  const percentage = ((value - min) / Math.max(max - min, Number.EPSILON)) * 100;
  return <label className={[styles.field, className].filter(Boolean).join(" ")}>
    <span className={styles.rangeHeader}><span>{label}</span><output className={styles.rangeValue}>{formatValue(value)}</output></span>
    <input className={styles.range} type="range" aria-label={label} min={min} max={max} step={step} value={value} disabled={disabled} style={{ "--range-position": `${percentage}%` } as CSSProperties} onChange={(event) => onValueChange(Number(event.currentTarget.value))} />
  </label>;
}
