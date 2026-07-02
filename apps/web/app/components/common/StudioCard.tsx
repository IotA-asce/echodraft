import type { ReactNode } from "react";

export function StudioCard({
  title,
  eyebrow,
  description,
  children,
}: {
  title?: string;
  eyebrow?: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <article className="studio-card">
      {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
      {title ? <h3>{title}</h3> : null}
      {description ? <p className="capability">{description}</p> : null}
      {children}
    </article>
  );
}
