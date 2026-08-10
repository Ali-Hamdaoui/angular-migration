'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiClientError, getBackendBaseUrl } from '@/api/client';
import { decideG01, getProductionPreflight } from '@/api/preflights';
import { createAuthoritativeRun, getAuthoritativeRunState, startAuthoritativeRun } from '@/api/runs';
import { GateDecisionPanel } from '@/components/gates/GateDecisionPanel';
import {
  GateReview,
  type ArtifactLink,
  type GateReviewModel,
  type GateReviewStatus,
} from '@/components/gates/GateReview';
import { StatusPill } from '@/components/StatusPill';
import { usePreflightEvents } from '@/hooks/usePreflightEvents';
import { gateDefinition } from '@/presentation/gates';
import { presentStatus } from '@/presentation/status';
import type { G01Decision, ProductionPreflight } from '@/types/preflight';
import styles from './G01ReviewPanel.module.css';

type Notice = { tone: 'success' | 'info' | 'error'; title: string; detail?: string; reloadLabel?: string };
type Snapshot = ProductionPreflight['snapshot'];
type EvidenceFreshness = 'current' | 'reload_required';

const ACTIVE_RUN_STORAGE_KEY = 'amfa.activeRunId';

const ARTIFACT_TITLES: Record<string, string> = {
  'preflight_result.json': 'Production readiness result',
  'preflight_request.json': 'Readiness request',
  'environment_capability_summary.json': 'Environment capability summary',
  'path_safety_report.json': 'Path safety report',
  'eligibility_result.json': 'Eligibility result',
};

const REQUIRED_ARTIFACTS = [
  'preflight_request.json',
  'environment_capability_summary.json',
  'path_safety_report.json',
  'eligibility_result.json',
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isValidTimestamp(value: unknown): value is string {
  return isNonEmptyString(value) && Number.isFinite(Date.parse(value));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isValidArtifact(value: unknown): value is Snapshot['artifacts'][string] {
  return isRecord(value)
    && isNonEmptyString(value.artifact_id)
    && isNonEmptyString(value.checksum)
    && isNonEmptyString(value.relative_path);
}

function isValidDecisionHistory(value: unknown, snapshot: Snapshot): boolean {
  return Array.isArray(value) && value.every((entry) => isRecord(entry)
    && isNonEmptyString(entry.decision_id)
    && entry.preflight_id === snapshot.preflight_id
    && entry.gate_id === 'G01'
    && ['approved', 'approved_with_comment', 'modification_requested', 'rejected'].includes(String(entry.decision))
    && isNonEmptyString(entry.actor)
    && (entry.comment === null || typeof entry.comment === 'string')
    && isValidTimestamp(entry.decided_at)
    && entry.input_checksum === snapshot.input_checksum
    && entry.artifact_set_checksum === snapshot.artifact_set_checksum
    && Number.isInteger(entry.state_version)
    && Number(entry.state_version) >= 1
    && typeof entry.idempotent_replay === 'boolean');
}

function isValidG01Package(snapshot: Snapshot): boolean {
  if (!isRecord(snapshot)) return false;
  const artifacts = snapshot.artifacts;
  return snapshot.gate_id === 'G01'
    && isNonEmptyString(snapshot.preflight_id)
    && isNonEmptyString(snapshot.gate_version)
    && Number.isInteger(snapshot.state_version)
    && snapshot.state_version >= 1
    && isValidTimestamp(snapshot.created_at)
    && isValidTimestamp(snapshot.expires_at)
    && isNonEmptyString(snapshot.input_checksum)
    && isNonEmptyString(snapshot.artifact_set_checksum)
    && isNonEmptyString(snapshot.source_path)
    && isNonEmptyString(snapshot.target_output_path)
    && isNonEmptyString(snapshot.target_reservation_id)
    && isStringArray(snapshot.blockers)
    && isStringArray(snapshot.warnings)
    && isRecord(artifacts)
    && Object.values(artifacts).every(isValidArtifact)
    && REQUIRED_ARTIFACTS.every((name) => isValidArtifact(artifacts[name]))
    && isValidDecisionHistory(snapshot.decision_history, snapshot);
}

function detailFor(error: unknown, fallback: string, reloadLabel?: string): Notice {
  if (error instanceof ApiClientError) {
    return { tone: 'error', title: fallback, detail: error.responseBody || error.message, reloadLabel };
  }
  return {
    tone: 'error',
    title: fallback,
    detail: error instanceof Error ? error.message : undefined,
    reloadLabel,
  };
}

function persistedRunId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY)?.trim() || null;
  } catch {
    return null;
  }
}

function isExpired(expiresAt: string, now: number): boolean {
  const expires = Date.parse(expiresAt);
  return Number.isFinite(expires) && expires <= now;
}

function reviewStatus(snapshot: Snapshot, now = Date.now()): GateReviewStatus {
  const approval = snapshot.approval_status as string;
  const status = snapshot.status as string;

  if (!isValidG01Package(snapshot)) return 'unknown';
  if (!Number.isFinite(Date.parse(snapshot.expires_at))) return 'unknown';
  if (approval === 'expired' || status === 'expired' || isExpired(snapshot.expires_at, now)) return 'expired';
  if (approval === 'stale' || status === 'stale') return 'stale';

  if (approval === 'approved' || approval === 'approved_with_comment') {
    return status === 'passed' || status === 'passed_with_warnings' ? 'approved' : 'unknown';
  }
  if (approval === 'rejected') {
    return ['passed', 'passed_with_warnings', 'blocked'].includes(status) ? 'rejected' : 'unknown';
  }
  if (approval === 'modification_requested') {
    return ['passed', 'passed_with_warnings', 'blocked'].includes(status) ? 'modification_requested' : 'unknown';
  }
  if (approval === 'pending' && ['passed', 'passed_with_warnings', 'blocked'].includes(status)) return 'pending';
  return 'unknown';
}

function shouldReplace(current: ProductionPreflight, incoming: ProductionPreflight): boolean {
  if (!isValidG01Package(current.snapshot)) return true;
  if (incoming.snapshot.state_version !== current.snapshot.state_version) {
    return incoming.snapshot.state_version > current.snapshot.state_version;
  }
  const currentStatus = reviewStatus(current.snapshot);
  const incomingStatus = reviewStatus(incoming.snapshot);
  if (currentStatus !== 'pending' && currentStatus !== 'unknown' && incomingStatus === 'pending') return false;
  return true;
}

function hasSameBindings(left: Snapshot, right: Snapshot): boolean {
  return left.preflight_id === right.preflight_id
    && left.gate_id === right.gate_id
    && left.input_checksum === right.input_checksum
    && left.artifact_set_checksum === right.artifact_set_checksum;
}

function outcomeFor(snapshot: Snapshot, status: GateReviewStatus): GateReviewModel['outcome'] {
  const latestDecision = Array.isArray(snapshot.decision_history) ? snapshot.decision_history.at(-1) : undefined;
  const comment = latestDecision?.comment ?? null;
  switch (status) {
    case 'approved':
      return {
        label: snapshot.approval_status === 'approved_with_comment' ? 'Approved with comment' : 'Approved',
        consequence: 'G01 approval authorizes creation and start of the authoritative run.',
        comment,
      };
    case 'rejected':
      return { label: 'Rejected', consequence: 'The migration run is not authorized from this evidence.', comment };
    case 'modification_requested':
      return { label: 'Modification requested', consequence: 'Update the readiness evidence before requesting another decision.', comment };
    case 'stale':
      return { label: 'Stale', consequence: 'This evidence is no longer current and cannot authorize a decision or run.', comment };
    case 'expired':
      return { label: 'Expired', consequence: 'This preflight has expired and new readiness evidence is required.', comment };
    case 'unknown':
      return { label: 'Review unavailable', consequence: 'The authoritative state is not recognized. Decisions and run creation are unavailable.', comment };
    default:
      return undefined;
  }
}

function buildReview(
  snapshot: Snapshot,
  streamStatus: string,
  lastEventId: number | null,
  status: GateReviewStatus,
): {
  artifactLinks: Record<string, ArtifactLink>;
  model: GateReviewModel;
} {
  const definition = gateDefinition('G01');
  const artifacts = isRecord(snapshot.artifacts)
    ? Object.entries(snapshot.artifacts).filter((entry): entry is [string, Snapshot['artifacts'][string]] => isValidArtifact(entry[1]))
    : [];
  const artifactLinks: Record<string, ArtifactLink> = {};

  const evidenceGroups = artifacts.map(([name, artifact]) => {
    const title = ARTIFACT_TITLES[name] ?? name;
    artifactLinks[artifact.artifact_id] = {
      href: `${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`,
      label: `Open ${title}`,
    };
    return {
      title,
      summary: 'Available evidence',
      artifactIds: [artifact.artifact_id],
      status: presentStatus('AVAILABLE'),
    };
  });

  const verified = [
    `Authoritative readiness outcome: ${presentStatus(snapshot.status).label}.`,
    `Source is read-only: ${snapshot.source_path}`,
    snapshot.target_reservation_id
      ? `Target is reserved output: ${snapshot.target_output_path}`
      : `Target output boundary: ${snapshot.target_output_path}`,
  ];

  const technicalBindings = [
    { label: 'Preflight ID', value: snapshot.preflight_id },
    { label: 'Raw preflight status', value: snapshot.status },
    { label: 'Raw approval status', value: snapshot.approval_status },
    { label: 'Gate version', value: snapshot.gate_version },
    { label: 'State version', value: String(snapshot.state_version) },
    { label: 'Input checksum', value: snapshot.input_checksum },
    { label: 'Artifact-set checksum', value: snapshot.artifact_set_checksum },
    { label: 'Target reservation ID', value: snapshot.target_reservation_id ?? 'Unavailable' },
    { label: 'Created at', value: snapshot.created_at },
    { label: 'Expires at', value: snapshot.expires_at },
    { label: 'Event stream status', value: streamStatus },
    { label: 'Event stream ID', value: lastEventId === null ? 'Unavailable' : String(lastEventId) },
    { label: 'Decision history entries', value: Array.isArray(snapshot.decision_history) ? String(snapshot.decision_history.length) : 'Unavailable' },
    ...artifacts.flatMap(([name, artifact]) => [
      { label: `${name} artifact ID`, value: artifact.artifact_id },
      { label: `${name} path`, value: artifact.relative_path },
      { label: `${name} checksum`, value: artifact.checksum },
    ]),
  ];

  return {
    artifactLinks,
    model: {
      gateId: 'G01',
      status,
      title: 'G01 production readiness',
      purpose: definition.purpose,
      consequence: 'Approval permits a separate action that creates a backend-owned run while the source remains read-only.',
      requiredDecision: status === 'pending'
        ? definition.decision
        : status === 'unknown'
          ? 'Decision authority is unavailable until a complete, current G01 evidence package is loaded.'
          : 'The backend has recorded a terminal outcome; no further reviewer decision is permitted.',
      verified,
      blockers: isStringArray(snapshot.blockers) ? snapshot.blockers : [],
      warnings: isStringArray(snapshot.warnings) ? snapshot.warnings : [],
      evidenceGroups,
      technicalBindings,
      outcome: outcomeFor(snapshot, status),
    },
  };
}

export function G01ReviewPanel({
  actor = 'control-tower',
  preflight,
}: {
  actor?: string;
  preflight: ProductionPreflight;
}) {
  const router = useRouter();
  const expectedPreflightId = preflight.snapshot.preflight_id;
  const [current, setCurrent] = useState(preflight);
  const currentRef = useRef(preflight);
  const [freshness, setFreshness] = useState<EvidenceFreshness>('current');
  const freshnessRef = useRef<EvidenceFreshness>('current');
  const [comment, setComment] = useState('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<G01Decision | null>(null);
  const [startingRun, setStartingRun] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const acceptRefresh = useCallback((incoming: ProductionPreflight): boolean => {
    if (!isValidG01Package(incoming.snapshot)) return false;
    if (incoming.snapshot.preflight_id !== expectedPreflightId) return false;
    if (!shouldReplace(currentRef.current, incoming)) return false;
    currentRef.current = incoming;
    setCurrent(incoming);
    freshnessRef.current = 'current';
    setFreshness('current');
    setNotice((value) => value?.reloadLabel ? null : value);
    return true;
  }, [expectedPreflightId]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const accepted = acceptRefresh(await getProductionPreflight(preflight.snapshot.preflight_id));
      if (!accepted) {
        setNotice({
          tone: 'error',
          title: 'Refreshed G01 evidence was not authoritative.',
          detail: 'The returned evidence was incomplete, inconsistent, or older than the currently displayed state.',
          reloadLabel: 'Reload G01 evidence',
        });
      }
    } catch (error) {
      setNotice(detailFor(error, 'Unable to refresh G01 evidence.', 'Reload G01 evidence'));
    } finally {
      setRefreshing(false);
    }
  }, [acceptRefresh, preflight.snapshot.preflight_id]);

  const stream = usePreflightEvents(preflight.snapshot.preflight_id, refresh);
  const { snapshot } = current;
  const status = freshness === 'current' ? reviewStatus(snapshot, now) : 'unknown';
  const canStart = status === 'approved'
    && (snapshot.approval_status === 'approved' || snapshot.approval_status === 'approved_with_comment');
  const { artifactLinks, model } = buildReview(snapshot, stream.status, stream.lastEventId, status);

  useEffect(() => {
    if (status === 'expired' || status === 'unknown') return;
    const expiresAt = Date.parse(snapshot.expires_at);
    if (!Number.isFinite(expiresAt)) return;
    const delay = Math.max(0, Math.min(expiresAt - Date.now(), 2_147_483_647));
    const timeout = window.setTimeout(() => setNow(Date.now()), delay);
    return () => window.clearTimeout(timeout);
  }, [now, snapshot.expires_at, status]);

  function invalidateStaleAction(expectedStatus: GateReviewStatus): boolean {
    const latest = currentRef.current.snapshot;
    const freshStatus = freshnessRef.current === 'current' ? reviewStatus(latest) : 'unknown';
    const displayedStateIsCurrent = latest.state_version === snapshot.state_version && hasSameBindings(latest, snapshot);
    if (freshStatus === expectedStatus && displayedStateIsCurrent) return false;
    setNow(Date.now());
    setNotice({
      tone: 'info',
      title: freshStatus === 'expired'
        ? 'This preflight has expired. Refresh evidence before continuing.'
        : 'Evidence is no longer actionable. Review the current gate status.',
    });
    return true;
  }

  async function submit(decision: G01Decision) {
    if (invalidateStaleAction('pending')) return;
    setBusy(decision);
    setNotice(null);
    const submitted = snapshot;
    const payloadComment = comment.trim() ? comment : null;
    try {
      const result = await decideG01(submitted.preflight_id, {
        gate_id: submitted.gate_id,
        decision,
        expected_state_version: submitted.state_version,
        input_checksum: submitted.input_checksum,
        artifact_set_checksum: submitted.artifact_set_checksum,
        idempotency_key: `g01-${submitted.preflight_id}-${decision}`,
        actor,
        comment: payloadComment,
      });
      const latest = currentRef.current;
      const latestStatus = freshnessRef.current === 'current' ? reviewStatus(latest.snapshot) : 'unknown';
      const updated: ProductionPreflight = {
        ...latest,
        snapshot: {
          ...latest.snapshot,
          state_version: result.state_version,
          approval_status: result.decision,
          decision_history: [...latest.snapshot.decision_history, result],
        },
      };
      const resultIsCurrent = result.preflight_id === submitted.preflight_id
        && result.gate_id === submitted.gate_id
        && result.decision === decision
        && result.input_checksum === submitted.input_checksum
        && result.artifact_set_checksum === submitted.artifact_set_checksum
        && latest.snapshot.preflight_id === submitted.preflight_id
        && latest.snapshot.gate_id === submitted.gate_id
        && latest.snapshot.input_checksum === submitted.input_checksum
        && latest.snapshot.artifact_set_checksum === submitted.artifact_set_checksum
        && Number.isInteger(result.state_version)
        && result.state_version >= latest.snapshot.state_version
        && latestStatus === 'pending'
        && !latest.snapshot.decision_history.some((entry) => entry.decision_id === result.decision_id)
        && isValidG01Package(updated.snapshot);
      if (!resultIsCurrent) {
        setNotice({ tone: 'info', title: 'A newer G01 state superseded this decision response.' });
        return;
      }
      currentRef.current = updated;
      setCurrent(updated);
      freshnessRef.current = 'current';
      setFreshness('current');
      setNotice({
        tone: 'success',
        title: `G01 ${result.decision.replaceAll('_', ' ')}${result.idempotent_replay ? ' (replayed)' : ''}.`,
      });
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 409) {
        setRefreshing(true);
        try {
          const authoritative = await getProductionPreflight(submitted.preflight_id);
          if (acceptRefresh(authoritative)) {
            setNotice({ tone: 'info', title: 'Evidence changed. Review the updated evidence and decide again.' });
          } else {
            freshnessRef.current = 'reload_required';
            setFreshness('reload_required');
            setNotice({ tone: 'error', title: 'Updated G01 evidence was not authoritative.', reloadLabel: 'Reload G01 evidence' });
          }
        } catch (reloadError) {
          freshnessRef.current = 'reload_required';
          setFreshness('reload_required');
          setNotice(detailFor(
            reloadError,
            'Updated G01 evidence could not be loaded.',
            'Reload G01 evidence',
          ));
        } finally {
          setRefreshing(false);
        }
      } else {
        setNotice(detailFor(error, 'G01 decision could not be recorded. Refresh evidence and retry.', 'Reload G01 evidence'));
      }
    } finally {
      setBusy(null);
    }
  }

  function approve() {
    void submit(comment.trim() ? 'approved_with_comment' : 'approved');
  }

  async function handleStartAuthoritativeRun() {
    if (invalidateStaleAction('approved')) return;
    setStartingRun(true);
    setNotice(null);
    try {
      const created = await createAuthoritativeRun({
        preflight_id: snapshot.preflight_id,
        input_checksum: snapshot.input_checksum,
        artifact_set_checksum: snapshot.artifact_set_checksum,
        idempotency_key: `run-create-${snapshot.preflight_id}`,
        actor,
        client_constraints: {
          preserve_ui: true,
          preserve_behavior: true,
          preserve_business_logic: true,
          preserve_api_contracts: true,
          preserve_authentication_authorization: true,
          allow_optional_modernization: false,
        },
        pricing_snapshot: {},
      });
      const started = await startAuthoritativeRun(created.run_id, {
        expected_state_version: created.state_version,
        idempotency_key: `run-start-${created.run_id}`,
        actor,
      });
      window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, started.run_id);
      router.push(`/?run_id=${encodeURIComponent(started.run_id)}`);
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 409 && error.responseBody?.includes('ACTIVE_RUN_EXISTS')) {
        const existingRunId = persistedRunId();
        if (existingRunId) {
          try {
            await getAuthoritativeRunState(existingRunId);
            router.push(`/?run_id=${encodeURIComponent(existingRunId)}`);
            return;
          } catch {
            // Retain the authoritative conflict when the persisted run cannot be reopened.
          }
        }
      }
      setNotice(detailFor(error, 'The authoritative run could not be started.'));
    } finally {
      setStartingRun(false);
    }
  }

  const decisionPanel = status === 'pending' ? (
    <GateDecisionPanel
      comment={comment}
      onCommentChange={(event) => setComment(event.target.value)}
      onApprove={approve}
      onRequestModification={() => void submit('modification_requested')}
      onReject={() => void submit('rejected')}
      busy={busy !== null || startingRun}
      approveDisabled={snapshot.status === 'blocked'}
      headingLevel={2}
    />
  ) : undefined;

  return (
    <main className={styles.page}>
      <div className={styles.content}>
        <GateReview model={model} artifactLinks={artifactLinks} decisionPanel={decisionPanel} headingLevel={1} />

        {status !== 'pending' && status !== 'unknown' ? (
          <section className={styles.runCard} aria-labelledby="run-title">
            <p className={styles.eyebrow}>Authoritative run</p>
            <h2 id="run-title">Create and start the authoritative run</h2>
            <p>
              {canStart
                ? 'G01 is approved. This action creates and starts the backend-owned run; the source stays read-only and output is run-owned.'
                : 'This terminal outcome does not authorize creation or start of an authoritative run.'}
            </p>
            <button
              type="button"
              disabled={!canStart || startingRun || busy !== null}
              onClick={handleStartAuthoritativeRun}
            >
              {startingRun ? 'Creating authoritative run...' : 'Create and start authoritative run'}
            </button>
          </section>
        ) : null}

        {notice ? (
          <section
            className={styles.notice}
            data-tone={notice.tone}
            role={notice.tone === 'error' ? 'alert' : 'status'}
          >
            <strong>{notice.title}</strong>
            {notice.detail ? <p>{notice.detail}</p> : null}
            {notice.reloadLabel ? (
              <button type="button" onClick={() => void refresh()} disabled={refreshing}>
                {refreshing ? 'Reloading G01 evidence...' : notice.reloadLabel}
              </button>
            ) : null}
          </section>
        ) : null}

        <footer className={styles.footer}>
          <div className={styles.connection}>
            <span>Evidence connection</span>
            <StatusPill status={presentStatus(stream.status)} />
          </div>
          <button type="button" onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? 'Refreshing evidence...' : 'Refresh evidence'}
          </button>
        </footer>
      </div>
    </main>
  );
}
