import { useId, type ReactNode } from 'react';
import { StatusPill } from '@/components/StatusPill';
import { TechnicalDetails } from '@/components/control-tower/TechnicalDetails';
import type { GateId } from '@/presentation/gates';
import type { StatusPresentation } from '@/presentation/status';
import styles from './GateReview.module.css';

export interface GateEvidenceGroup {
  title: string;
  summary: string;
  artifactIds: string[];
  status: StatusPresentation;
}

export type GateReviewStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'modification_requested'
  | 'stale'
  | 'expired'
  | 'unknown';

export interface GateReviewModel {
  gateId: GateId;
  status: GateReviewStatus;
  title: string;
  purpose: string;
  consequence?: string;
  requiredDecision: string;
  verified: string[];
  warnings: string[];
  blockers: string[];
  evidenceGroups: GateEvidenceGroup[];
  technicalBindings: Array<{ label: string; value: string }>;
  outcome?: { label: string; consequence: string; comment?: string | null };
}

export interface ArtifactLink {
  href: string;
  label: string;
}

const TERMINAL_PRESENTATIONS: Record<Exclude<GateReviewStatus, 'pending'>, StatusPresentation> = {
  approved: { label: 'Approved', tone: 'success', raw: 'approved' },
  rejected: { label: 'Rejected', tone: 'danger', raw: 'rejected' },
  modification_requested: { label: 'Modification requested', tone: 'warning', raw: 'modification_requested' },
  stale: { label: 'Stale', tone: 'warning', raw: 'stale' },
  expired: { label: 'Expired', tone: 'warning', raw: 'expired' },
  unknown: { label: 'Unknown status', tone: 'neutral', raw: 'unknown' },
};

const PENDING_PRESENTATION: StatusPresentation = {
  label: 'Decision required',
  tone: 'warning',
  raw: 'pending',
};

function FindingList({ empty, items }: { empty: string; items: string[] }) {
  return items.length > 0 ? (
    <ul className={styles.findingList}>{items.map((item) => <li key={item}>{item}</li>)}</ul>
  ) : <p className={styles.empty}>{empty}</p>;
}

export function GateReview({
  artifactLinks = {},
  decisionPanel,
  model,
}: {
  artifactLinks?: Record<string, ArtifactLink>;
  decisionPanel?: ReactNode;
  model: GateReviewModel;
}) {
  const id = useId();
  const ids = {
    title: `${id}-title`,
    purpose: `${id}-purpose`,
    decision: `${id}-decision`,
    verified: `${id}-verified`,
    blockers: `${id}-blockers`,
    warnings: `${id}-warnings`,
    evidence: `${id}-evidence`,
  };
  const status = model.status === 'pending' ? PENDING_PRESENTATION : TERMINAL_PRESENTATIONS[model.status];
  const outcome = model.status === 'pending' ? null : model.outcome ?? {
    label: status.label,
    consequence: 'This gate is terminal. No reviewer decision is available.',
  };

  return (
    <article className={styles.review} aria-labelledby={ids.title}>
      <header className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>{model.gateId} governed review</p>
          <h1 id={ids.title}>{model.title}</h1>
        </div>
        <StatusPill status={status} />
      </header>

      <section className={styles.section} aria-labelledby={ids.purpose}>
        <h2 id={ids.purpose}>Why this review exists</h2>
        <p>{model.purpose}</p>
        {model.consequence ? <p className={styles.consequence}>{model.consequence}</p> : null}
      </section>

      <section className={styles.section} aria-labelledby={ids.decision}>
        <h2 id={ids.decision}>{outcome ? 'Decision outcome' : 'Decision required'}</h2>
        <p>{model.requiredDecision}</p>
        {outcome ? (
          <div className={styles.outcome} data-status={model.status}>
            <h3>{outcome.label}</h3>
            <p>{outcome.consequence}</p>
            {outcome.comment ? <p className={styles.outcomeComment}><strong>Reviewer comment:</strong> {outcome.comment}</p> : null}
          </div>
        ) : null}
      </section>

      <section className={styles.section} aria-labelledby={ids.verified}>
        <h2 id={ids.verified}>Verified facts</h2>
        <FindingList items={model.verified} empty="No verified facts are available for this review." />
      </section>

      <section className={`${styles.section} ${styles.blockers}`} aria-labelledby={ids.blockers}>
        <h2 id={ids.blockers}>Blockers</h2>
        <FindingList items={model.blockers} empty="No blockers were reported." />
      </section>

      <section className={`${styles.section} ${styles.warnings}`} aria-labelledby={ids.warnings}>
        <h2 id={ids.warnings}>Warnings</h2>
        <FindingList items={model.warnings} empty="No warnings were reported." />
      </section>

      <section className={styles.section} aria-labelledby={ids.evidence}>
        <h2 id={ids.evidence}>Evidence</h2>
        {model.evidenceGroups.length > 0 ? (
          <div className={styles.evidenceGrid}>
            {model.evidenceGroups.map((group) => {
              const links = group.artifactIds.flatMap((artifactId) => {
                const link = artifactLinks[artifactId];
                return link ? [{ artifactId, link }] : [];
              });
              const missingLinkCount = group.artifactIds.length - links.length;
              return (
              <section className={styles.evidenceCard} key={`${group.title}-${group.artifactIds.join('-')}`}>
                <div className={styles.evidenceHeading}>
                  <h3>{group.title}</h3>
                  <StatusPill status={group.status} />
                </div>
                <p>{group.summary}</p>
                {links.length > 0 ? (
                  <ul className={styles.artifactLinks}>
                    {links.map(({ artifactId, link }) => <li key={artifactId}><a href={link.href}>{link.label}</a></li>)}
                  </ul>
                ) : null}
                {missingLinkCount > 0
                  ? <p className={styles.empty}>Artifact link metadata is unavailable for this evidence group.</p>
                  : group.artifactIds.length === 0
                    ? <p className={styles.empty}>No artifact links are available for this evidence group.</p>
                    : null}
              </section>
              );
            })}
          </div>
        ) : <p className={styles.empty}>No evidence groups are available for this review.</p>}
      </section>

      {model.status === 'pending' && decisionPanel ? <div className={styles.decisionRegion}>{decisionPanel}</div> : null}

      <TechnicalDetails title="Technical details">
        {model.technicalBindings.length > 0 ? (
          <dl className={styles.bindings}>
            {model.technicalBindings.map((binding, index) => (
              <div key={`${binding.label}-${index}`}><dt>{binding.label}</dt><dd><code>{binding.value}</code></dd></div>
            ))}
          </dl>
        ) : <p className={styles.empty}>No technical bindings are available.</p>}
      </TechnicalDetails>
    </article>
  );
}
