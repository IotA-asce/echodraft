"use client";

import { useEffect, useId, useRef, useState } from "react";
import styles from "./primitives.module.css";

export type SelectOption = { value: string; label: string; disabled?: boolean };

export function Select({ label, value, options, onValueChange, disabled = false, className }: { label: string; value: string; options: SelectOption[]; onValueChange: (value: string) => void; disabled?: boolean; className?: string }) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value));
  const [active, setActive] = useState(selectedIndex);
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const enabledIndex = (from: number, delta: number) => {
    if (!options.length) return 0;
    let next = from;
    do { next = (next + delta + options.length) % options.length; } while (options[next]?.disabled && next !== from);
    return next;
  };
  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onValueChange(option.value);
    setActive(index);
    setOpen(false);
    trigger.current?.focus();
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (["ArrowDown", "ArrowUp", "Home", "End", "Enter", " ", "Escape"].includes(event.key)) event.preventDefault();
    if (event.key === "Escape") { setOpen(false); return; }
    if (event.key === "Home") { setOpen(true); setActive(enabledIndex(-1, 1)); return; }
    if (event.key === "End") { setOpen(true); setActive(enabledIndex(0, -1)); return; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { setOpen(true); setActive((current) => enabledIndex(current, event.key === "ArrowDown" ? 1 : -1)); return; }
    if (event.key === "Enter" || event.key === " ") { if (open) choose(active); else { setActive(selectedIndex); setOpen(true); } return; }
    if (event.key.length === 1) {
      const match = options.findIndex((option) => !option.disabled && option.label.toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()));
      if (match >= 0) { setOpen(true); setActive(match); }
    }
  };
  return <div ref={root} className={[styles.field, className].filter(Boolean).join(" ")}>
    <span id={`${id}-label`}>{label}</span>
    <button ref={trigger} type="button" role="combobox" aria-labelledby={`${id}-label`} aria-controls={`${id}-listbox`} aria-expanded={open} aria-activedescendant={open ? `${id}-option-${active}` : undefined} className={styles.selectTrigger} disabled={disabled} onClick={() => { setActive(selectedIndex); setOpen((current) => !current); }} onKeyDown={onKeyDown}>
      <span>{selected?.label ?? "Select…"}</span><span aria-hidden className={[styles.chevron, open ? styles.chevronOpen : ""].join(" ")}>⌄</span>
    </button>
    {open ? <ul id={`${id}-listbox`} role="listbox" aria-labelledby={`${id}-label`} className={styles.listbox}>
      {options.map((option, index) => <li id={`${id}-option-${index}`} key={option.value} role="option" aria-selected={option.value === value} aria-disabled={option.disabled || undefined} className={[styles.option, index === active ? styles.optionActive : "", option.value === value ? styles.optionSelected : ""].filter(Boolean).join(" ")} onPointerMove={() => !option.disabled && setActive(index)} onPointerDown={(event) => event.preventDefault()} onClick={() => choose(index)}>
        <span aria-hidden className={styles.optionCheck}>✓</span><span>{option.label}</span>
      </li>)}
    </ul> : null}
  </div>;
}
