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
  headingLevel?: 2 | 3;
}

export function GateDecisionPanel({
  approveDisabled = false,
  busy,
  comment,
  headingLevel = 3,
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
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <section className={styles.decisionPanel} aria-labelledby={titleId}>
      <Heading id={titleId}>Reviewer controls</Heading>
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
