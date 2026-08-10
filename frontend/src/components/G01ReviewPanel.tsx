'use client';

import { useCallback, useEffect, useState } from 'react';
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

const ACTIVE_RUN_STORAGE_KEY = 'amfa.activeRunId';

const ARTIFACT_TITLES: Record<string, string> = {
  'preflight_result.json': 'Production readiness result',
  'preflight_request.json': 'Readiness request',
  'environment_capability_summary.json': 'Environment capability summary',
  'path_safety_report.json': 'Path safety report',
  'eligibility_result.json': 'Eligibility result',
};

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

  if (snapshot.gate_id !== 'G01') return 'unknown';
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
  if (incoming.snapshot.state_version !== current.snapshot.state_version) {
    return incoming.snapshot.state_version > current.snapshot.state_version;
  }
  const currentStatus = reviewStatus(current.snapshot);
  const incomingStatus = reviewStatus(incoming.snapshot);
  if (currentStatus !== 'pending' && currentStatus !== 'unknown' && incomingStatus === 'pending') return false;
  return true;
}

function outcomeFor(snapshot: Snapshot, status: GateReviewStatus): GateReviewModel['outcome'] {
  const latestDecision = snapshot.decision_history.at(-1);
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

function buildReview(snapshot: Snapshot, streamStatus: string, lastEventId: number | null, now: number): {
  artifactLinks: Record<string, ArtifactLink>;
  model: GateReviewModel;
} {
  const definition = gateDefinition('G01');
  const status = reviewStatus(snapshot, now);
  const artifacts = Object.entries(snapshot.artifacts);
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
        : 'The backend has recorded a terminal outcome; no further reviewer decision is permitted.',
      verified,
      blockers: snapshot.blockers,
      warnings: snapshot.warnings,
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
  const [current, setCurrent] = useState(preflight);
  const [comment, setComment] = useState('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<G01Decision | null>(null);
  const [startingRun, setStartingRun] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const acceptRefresh = useCallback((incoming: ProductionPreflight) => {
    setCurrent((value) => shouldReplace(value, incoming) ? incoming : value);
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      acceptRefresh(await getProductionPreflight(preflight.snapshot.preflight_id));
    } catch (error) {
      setNotice(detailFor(error, 'Unable to refresh G01 evidence.', 'Reload G01 evidence'));
    } finally {
      setRefreshing(false);
    }
  }, [acceptRefresh, preflight.snapshot.preflight_id]);

  const stream = usePreflightEvents(preflight.snapshot.preflight_id, refresh);
  const { snapshot } = current;
  const status = reviewStatus(snapshot, now);
  const canStart = status === 'approved'
    && (snapshot.approval_status === 'approved' || snapshot.approval_status === 'approved_with_comment');
  const { artifactLinks, model } = buildReview(snapshot, stream.status, stream.lastEventId, now);

  useEffect(() => {
    if (status === 'expired' || status === 'unknown') return;
    const expiresAt = Date.parse(snapshot.expires_at);
    if (!Number.isFinite(expiresAt)) return;
    const delay = Math.max(0, Math.min(expiresAt - Date.now(), 2_147_483_647));
    const timeout = window.setTimeout(() => setNow(Date.now()), delay);
    return () => window.clearTimeout(timeout);
  }, [now, snapshot.expires_at, status]);

  function invalidateStaleAction(expectedStatus: GateReviewStatus): boolean {
    const freshStatus = reviewStatus(snapshot);
    if (freshStatus === expectedStatus) return false;
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
    const payloadComment = comment.trim() ? comment : null;
    try {
      const result = await decideG01(snapshot.preflight_id, {
        gate_id: snapshot.gate_id,
        decision,
        expected_state_version: snapshot.state_version,
        input_checksum: snapshot.input_checksum,
        artifact_set_checksum: snapshot.artifact_set_checksum,
        idempotency_key: `g01-${snapshot.preflight_id}-${decision}`,
        actor,
        comment: payloadComment,
      });
      setCurrent((value) => ({
        ...value,
        snapshot: {
          ...value.snapshot,
          state_version: result.state_version,
          approval_status: result.decision,
          decision_history: [...value.snapshot.decision_history, result],
        },
      }));
      setNotice({
        tone: 'success',
        title: `G01 ${result.decision.replaceAll('_', ' ')}${result.idempotent_replay ? ' (replayed)' : ''}.`,
      });
    } catch (error) {
      if (error instanceof ApiClientError && error.status === 409) {
        setRefreshing(true);
        try {
          const authoritative = await getProductionPreflight(snapshot.preflight_id);
          acceptRefresh(authoritative);
          setNotice({ tone: 'info', title: 'Evidence changed. Review the updated evidence and decide again.' });
        } catch (reloadError) {
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
    />
  ) : undefined;

  return (
    <main className={styles.page}>
      <div className={styles.content}>
        <GateReview model={model} artifactLinks={artifactLinks} decisionPanel={decisionPanel} />

        {status !== 'pending' ? (
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
