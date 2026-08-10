import { useId, type ChangeEventHandler } from 'react';
import styles from './GateReview.module.css';

export interface GateDecisionPanelProps {
  comment: string;
  onCommentChange: ChangeEventHandler<HTMLTextAreaElement>;
  onApprove: () => void;
  onRequestModification: () => void;
  onReject: () => void;
  busy: boolean;
  approveDisabled?: boolean;
  modificationDisabled?: boolean;
  rejectDisabled?: boolean;
}

export function GateDecisionPanel({
  approveDisabled = false,
  busy,
  comment,
  modificationDisabled = false,
  onApprove,
  onCommentChange,
  onReject,
  onRequestModification,
  rejectDisabled = false,
}: GateDecisionPanelProps) {
  const id = useId();
  const titleId = `${id}-reviewer-controls`;
  const commentId = `${id}-reviewer-comment`;
  return (
    <section className={styles.decisionPanel} aria-labelledby={titleId}>
      <h2 id={titleId}>Reviewer controls</h2>
      <p>Record one backend-permitted decision against this exact evidence set.</p>
      <label htmlFor={commentId}>
        Reviewer comment
        <span>Optional for approval; include rationale for requested changes.</span>
      </label>
      <textarea
        id={commentId}
        aria-label="Reviewer comment"
        value={comment}
        onChange={onCommentChange}
        rows={5}
        disabled={busy}
      />
      <div className={styles.decisionActions}>
        <button type="button" onClick={onApprove} disabled={busy || approveDisabled}>Approve G01</button>
        <button type="button" onClick={onRequestModification} disabled={busy || modificationDisabled}>Request modification</button>
        <button type="button" onClick={onReject} disabled={busy || rejectDisabled}>Reject G01</button>
      </div>
    </section>
  );
}
