import type { FormEvent } from "react";

export function NewProjectPanel({
  title,
  author,
  rights,
  busy,
  onTitleChange,
  onAuthorChange,
  onRightsChange,
  onSubmit,
}: {
  title: string;
  author: string;
  rights: boolean;
  busy: boolean;
  onTitleChange: (value: string) => void;
  onAuthorChange: (value: string) => void;
  onRightsChange: (value: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="create-card" onSubmit={onSubmit}>
      <p className="eyebrow">New project</p>
      <h2>Open a production file</h2>
      <label>
        Title
        <input aria-label="Title" value={title} onChange={(event) => onTitleChange(event.target.value)} required />
      </label>
      <label>
        Author <span>optional</span>
        <input value={author} onChange={(event) => onAuthorChange(event.target.value)} />
      </label>
      <label className="rights-check">
        <input type="checkbox" checked={rights} onChange={(event) => onRightsChange(event.target.checked)} />
        <span>I confirm I have the rights to create this audiobook draft.</span>
      </label>
      <button disabled={busy || !rights || !title.trim()}>Create project</button>
    </form>
  );
}
