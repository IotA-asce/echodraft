import { useState } from "react";
import { Button, Modal } from "../../design-system";

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
  return (
    <><button type="button" className={className} disabled={disabled} onClick={() => setConfirming(true)}>{label}</button><Modal open={confirming} onOpenChange={setConfirming} title={confirmLabel ?? "Confirm action"} description={message} size="sm" footer={<><Button type="button" variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button><Button type="button" variant="destructive" disabled={disabled} onClick={() => { setConfirming(false); onConfirm(); }}>{confirmLabel ?? "Confirm"}</Button></>}><p>This action cannot be undone automatically.</p></Modal></>
  );
}
