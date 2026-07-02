import type { FormEvent } from "react";
import type { Comment, Issue } from "../../api";

export function IssueInspector({
  activeIssue,
  comments,
  onComment,
}: {
  activeIssue: Issue | null;
  comments: Comment[];
  onComment: (event: FormEvent<HTMLFormElement>) => void;
}) {
  if (!activeIssue) {
    return (
      <div className="issue-inspector empty">
        <strong>No discussion selected</strong>
        <p>Open an issue to add local review notes or line-level fix context.</p>
      </div>
    );
  }

  return (
    <div className="issue-inspector comment-box">
      <strong>{activeIssue.title}</strong>
      {comments.length ? comments.map((item) => <p key={item.id}>{item.body}</p>) : <p>No local notes yet.</p>}
      <form onSubmit={onComment}>
        <input name="comment" placeholder="Add a local review note" />
        <button>Add note</button>
      </form>
    </div>
  );
}
