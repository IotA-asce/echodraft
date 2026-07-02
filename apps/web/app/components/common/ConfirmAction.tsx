import { useState } from "react";

export function ConfirmAction({
  label,
  confirmLabel,
  message,
  className,
  disabled,
  onConfirm,
}: {
  label: string;
  confirmLabel?: string;
  message: string;
  className?: string;
  disabled?: boolean;
  onConfirm: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  if (confirming) {
    return (
      <span className="confirm-action">
        <small>{message}</small>
        <button
          type="button"
          className={className}
          disabled={disabled}
          onClick={() => {
            setConfirming(false);
            onConfirm();
          }}
        >
          {confirmLabel ?? "Confirm"}
        </button>
        <button type="button" className="small-button secondary" onClick={() => setConfirming(false)}>
          Cancel
        </button>
      </span>
    );
  }
  return (
    <button type="button" className={className} disabled={disabled} onClick={() => setConfirming(true)}>
      {label}
    </button>
  );
}
