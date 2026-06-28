export function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
  secondaryText,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  secondaryText?: string;
}) {
  return (
    <div className="empty-state studio-empty-state">
      <span aria-hidden="true">§</span>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
        {actionLabel && onAction ? (
          <button type="button" className="small-button" onClick={onAction}>
            {actionLabel}
          </button>
        ) : null}
        {secondaryText ? <small>{secondaryText}</small> : null}
      </div>
    </div>
  );
}
