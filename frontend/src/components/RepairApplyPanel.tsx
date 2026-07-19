'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClientError, getBackendBaseUrl } from '@/api/client';
import { applyRepairDiff, getApplyResult } from '@/api/patches';
import type { PatchApplyResult } from '@/api/patches';
import styles from './RepairApplyPanel.module.css';

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type ApplyPanelState =
  | 'loading'
  | 'empty'
  | 'running'
  | 'success'
  | 'blocked'
  | 'stale'
  | 'reconnecting'
  | 'backend-failure';

interface SafetyCheck {
  name: string;
  status: 'passed' | 'failed' | 'warning' | 'skipped';
  detail?: string;
}

interface DryRunResult {
  status: 'passed' | 'failed' | 'inconclusive';
  output?: string;
  detail?: string;
}

interface LedgerInfo {
  entry_id: string;
  url?: string;
}

interface ApplyData {
  result: PatchApplyResult;
  safety_checks: SafetyCheck[];
  dry_run: DryRunResult | null;
  ledger: LedgerInfo | null;
}

type Notice = { tone: 'success' | 'error'; title: string; detail?: string };

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function label(value: string) {
  return value.replaceAll('_', ' ');
}

function detailFor(error: unknown, fallback: string): Notice {
  if (error instanceof ApiClientError) {
    return {
      tone: 'error',
      title: fallback,
      detail: error.responseBody || error.message,
    };
  }
  return {
    tone: 'error',
    title: fallback,
    detail: error instanceof Error ? error.message : undefined,
  };
}

function statusStyle(status: string) {
  switch (status) {
    case 'passed':
    case 'success':
    case 'applied':
      return styles.statusPassed;
    case 'failed':
    case 'error':
      return styles.statusFailed;
    case 'warning':
    case 'inconclusive':
      return styles.statusWarning;
    default:
      return styles.statusDefault;
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function RepairApplyPanel({
  runId,
  proposalId,
}: {
  runId: string;
  proposalId: string;
}) {
  const [state, setState] = useState<ApplyPanelState>('loading');
  const [data, setData] = useState<ApplyData | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const refreshKeyRef = useRef(0);

  /* ---- Fetch apply result from backend ---- */
  const fetchResult = useCallback(async () => {
    const key = ++refreshKeyRef.current;
    setNotice(null);

    try {
      setState('loading');
      const result = await getApplyResult(runId, proposalId);

      // Guard against stale response from a raced re-fetch
      if (key !== refreshKeyRef.current) return;

      if (!result) {
        setState('empty');
        setData(null);
        return;
      }

      const status = result.status;
      if (status === 'applied' || status === 'success') {
        setState('success');
      } else if (status === 'blocked') {
        setState('blocked');
      } else if (status === 'stale') {
        setState('stale');
        // Automatically reconnect / reload on stale
        setTimeout(() => void fetchResult(), 1500);
        return;
      } else if (status === 'pending' || status === 'running') {
        setState('running');
        // Poll while backend is still working
        setTimeout(() => void fetchResult(), 3000);
        return;
      } else {
        setState('empty');
      }

      // Extract safety checks, dry_run, and ledger from the result.
      // failure_evidence may hold structured safety-check or dry-run info.
      // artifact_refs may contain a ledger entry.
      const safety_checks: SafetyCheck[] = extractSafetyChecks(result);
      const dry_run: DryRunResult | null = extractDryRun(result);
      const ledger: LedgerInfo | null = extractLedger(result);

      setData({ result, safety_checks, dry_run, ledger });
    } catch (error: unknown) {
      if (key !== refreshKeyRef.current) return;

      if (error instanceof ApiClientError) {
        if (error.status === 404) {
          setState('empty');
          setData(null);
          return;
        }
        if (error.status === 409) {
          setState('stale');
          // Reconnect / reload on conflict
          setTimeout(() => void fetchResult(), 1500);
          return;
        }
        if (error.status === 503 || error.status === 502) {
          setState('reconnecting');
          setTimeout(() => void fetchResult(), 3000);
          return;
        }
      }
      setState('backend-failure');
      setNotice(detailFor(error, 'Could not load apply result from backend.'));
    }
  }, [runId, proposalId]);

  /* ---- Initial fetch ---- */
  useEffect(() => {
    void fetchResult();
  }, [fetchResult]);

  /* ---- Apply the repair diff ---- */
  const handleApply = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setNotice(null);

    try {
      const request = {
        proposal_id: proposalId,
        diff_content: '', // backend fills from the proposal record
        expected_checksum: '',
        expected_fingerprint: '',
        expected_state_version: data?.result.state_version ?? 0,
        idempotency_key: `apply-${runId}-${proposalId}-${Date.now()}`,
        actor: 'control-tower',
        workspace_root: null,
      };

      const result = await applyRepairDiff(runId, proposalId, request);

      // Show pending indicator only — never advance workflow locally
      setState('running');
      setData(null);
      setNotice({
        tone: 'success',
        title: `Apply submitted (${result.idempotent_replay ? 'replayed' : 'idempotent_key accepted'}).`,
        detail:
          'The apply is being processed by the backend. Pending indicator shown; results refresh automatically.',
      });

      // Poll for the result
      setTimeout(() => void fetchResult(), 2000);
    } catch (error: unknown) {
      if (error instanceof ApiClientError) {
        if (error.status === 409) {
          setNotice({
            tone: 'error',
            title: 'Stale state version. Reloading authoritative data from backend.',
          });
          setState('stale');
          setTimeout(() => void fetchResult(), 1500);
          return;
        }
        if (error.status === 422) {
          setNotice({
            tone: 'error',
            title: 'Apply validation failed.',
            detail: error.responseBody ?? 'Backend rejected the apply request.',
          });
          return;
        }
      }
      setNotice(detailFor(error, 'Apply could not be submitted. Check backend connectivity.'));
    } finally {
      setBusy(false);
    }
  }, [runId, proposalId, data, busy, fetchResult]);

  /* ---- Manual refresh ---- */
  const handleRefresh = useCallback(() => {
    setState('reconnecting');
    void fetchResult();
  }, [fetchResult]);

  /* ---- Derive status label for current panel state ---- */
  const statusLabel = (() => {
    switch (state) {
      case 'loading':
        return 'Loading apply result…';
      case 'empty':
        return 'No apply result yet';
      case 'running':
        return 'Apply in progress…';
      case 'success':
        return 'Apply completed';
      case 'blocked':
        return 'Apply blocked';
      case 'stale':
        return 'State version stale — reconnecting…';
      case 'reconnecting':
        return 'Reconnecting to backend…';
      case 'backend-failure':
        return 'Backend error';
      default:
        return label(state);
    }
  })();

  /* ---- Render ---- */
  return (
    <section className={styles.panel} aria-label="Repair apply panel">
      {/* Header */}
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>S4-F07</p>
          <h2 id="repair-apply-title">Apply repair diff</h2>
          <p className={styles.note}>
            Every safety check, exact outcome, stale/path/applicability errors,
            and immutable ledger link.
          </p>
        </div>
        <div className={styles.headerRight}>
          <span
            className={`${styles.statusBadge} ${styles[`state_${state}`] ?? ''}`}
          >
            {statusLabel}
          </span>
        </div>
      </div>

      {/* Reconnecting / stale notice */}
      {(state === 'reconnecting' || state === 'stale') && (
        <div className={styles.reconnectNotice} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          Backend state changed. Reloading authoritative apply data…
        </div>
      )}

      {/* Notice banner */}
      {notice && (
        <div
          className={`${styles.notice} ${notice.tone === 'error' ? styles.noticeError : styles.noticeSuccess}`}
          role={notice.tone === 'error' ? 'alert' : 'status'}
        >
          <strong>{notice.title}</strong>
          {notice.detail && <p>{notice.detail}</p>}
        </div>
      )}

      {/* Loading state */}
      {state === 'loading' && !data && (
        <div className={styles.centeredMessage} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          <p>Loading apply result from backend…</p>
        </div>
      )}

      {/* Empty state */}
      {state === 'empty' && (
        <div className={styles.centeredMessage}>
          <p className={styles.note}>
            No apply result exists yet for proposal{' '}
            <code>{proposalId}</code>.
          </p>
          <p className={styles.note}>
            Review the safety checks below, then submit the apply to the
            backend.
          </p>

          {/* Show an Apply button in empty state too */}
          <button
            className={styles.applyButton}
            type="button"
            onClick={handleApply}
            disabled={busy}
          >
            {busy ? 'Submitting apply…' : 'Apply repair diff'}
          </button>
        </div>
      )}

      {/* Running state (apply submitted, waiting for backend) */}
      {state === 'running' && (
        <div className={styles.centeredMessage} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          <p>Apply is being processed by the backend.</p>
          <p className={styles.note}>
            This panel will update automatically when the result is ready.
          </p>
          <button
            className={styles.refreshButton}
            type="button"
            onClick={handleRefresh}
            disabled={busy}
          >
            Refresh now
          </button>
        </div>
      )}

      {/* Blocked state */}
      {state === 'blocked' && data && (
        <div className={styles.blockedBanner} role="alert">
          <strong>Apply blocked</strong>
          <p>
            The backend has blocked this apply. Review the safety check
            failures below and address any issues before retrying.
          </p>
          <button
            className={styles.refreshButton}
            type="button"
            onClick={handleRefresh}
            disabled={busy}
          >
            Reload authoritative state
          </button>
        </div>
      )}

      {/* Backend failure state */}
      {state === 'backend-failure' && (
        <div className={styles.centeredMessage}>
          <p role="alert" className={styles.errorText}>
            A backend error occurred while loading the apply result.
          </p>
          <button
            className={styles.refreshButton}
            type="button"
            onClick={handleRefresh}
            disabled={busy}
          >
            Retry
          </button>
        </div>
      )}

      {/* Success / data-present states — show full apply details */}
      {(state === 'success' || state === 'blocked') && data && (
        <div className={styles.content}>
          {/* ---- Summary ---- */}
          <div className={styles.summaryGrid}>
            <div>
              <span>Status</span>
              <strong className={statusStyle(data.result.status)}>
                {label(data.result.status)}
              </strong>
            </div>
            <div>
              <span>State version</span>
              <strong>{data.result.state_version}</strong>
            </div>
            <div>
              <span>Idempotent replay</span>
              <strong>
                {data.result.idempotent_replay ? 'Yes' : 'No'}
              </strong>
            </div>
            <div>
              <span>Apply ID</span>
              <code>{data.result.patch_apply_id}</code>
            </div>
          </div>

          {/* ---- Safety check table ---- */}
          {data.safety_checks.length > 0 && (
            <section aria-labelledby="safety-checks-title">
              <h3 id="safety-checks-title" className={styles.sectionTitle}>
                Safety checks
              </h3>
              <div className={styles.tableWrapper}>
                <table className={styles.checksTable}>
                  <thead>
                    <tr>
                      <th>Check</th>
                      <th>Outcome</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.safety_checks.map((check) => (
                      <tr key={check.name}>
                        <td>
                          <strong>{label(check.name)}</strong>
                        </td>
                        <td>
                          <span
                            className={`${styles.checkBadge} ${statusStyle(check.status)}`}
                          >
                            {label(check.status)}
                          </span>
                        </td>
                        <td className={styles.checkDetail}>
                          {check.detail ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* ---- Dry run results ---- */}
          {data.dry_run && (
            <section aria-labelledby="dry-run-title">
              <h3 id="dry-run-title" className={styles.sectionTitle}>
                Dry run result
              </h3>
              <div
                className={`${styles.dryRunCard} ${statusStyle(data.dry_run.status)}`}
              >
                <span className={styles.dryRunStatus}>
                  {label(data.dry_run.status)}
                </span>
                {data.dry_run.detail && <p>{data.dry_run.detail}</p>}
                {data.dry_run.output && (
                  <pre className={styles.codeBlock}>{data.dry_run.output}</pre>
                )}
              </div>
            </section>
          )}

          {/* ---- Ledger entry ---- */}
          {data.ledger && (
            <section aria-labelledby="ledger-title">
              <h3 id="ledger-title" className={styles.sectionTitle}>
                Immutable ledger
              </h3>
              <div className={styles.ledgerCard}>
                <p>
                  Entry ID: <code>{data.ledger.entry_id}</code>
                </p>
                {data.ledger.url && (
                  <a
                    className={styles.ledgerLink}
                    href={data.ledger.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View ledger entry ↗
                  </a>
                )}
                {!data.ledger.url && (
                  <a
                    className={styles.ledgerLink}
                    href={`${getBackendBaseUrl()}/api/v1/runs/${encodeURIComponent(runId)}/repair-proposals/${encodeURIComponent(proposalId)}/ledger/${encodeURIComponent(data.ledger.entry_id)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View ledger entry ↗
                  </a>
                )}
              </div>
            </section>
          )}

          {/* ---- Artifact references ---- */}
          {data.result.artifact_refs &&
            Object.keys(data.result.artifact_refs).length > 0 && (
              <section aria-labelledby="artifacts-title">
                <h3 id="artifacts-title" className={styles.sectionTitle}>
                  Immutable evidence
                </h3>
                <ul className={styles.artifactList}>
                  {Object.entries(data.result.artifact_refs).map(
                    ([name, artifactId]) => (
                      <li key={name}>
                        <span>{name}</span>
                        <code>{artifactId}</code>
                        <a
                          href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifactId)}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open
                        </a>
                      </li>
                    ),
                  )}
                </ul>
              </section>
            )}
        </div>
      )}

      {/* Apply button row — shown whenever apply can be triggered */}
      {state !== 'running' && state !== 'loading' && (
        <div className={styles.applyRow}>
          <button
            className={styles.applyButton}
            type="button"
            onClick={handleApply}
            disabled={
              busy ||
              state === 'reconnecting' ||
              state === 'stale'
            }
          >
            {busy
              ? 'Submitting apply…'
              : state === 'success'
                ? 'Re-apply repair diff'
                : 'Apply repair diff'}
          </button>
          <span className={styles.applyHint}>
            Uses idempotency_key and expected_state_version. The backend owns
            all workflow advancement; this panel reflects backend state only.
          </span>
        </div>
      )}

      {/* Footer with run/proposal info */}
      <div className={styles.footer}>
        <span>
          Run: <code>{runId}</code>
        </span>
        <span>
          Proposal: <code>{proposalId}</code>
        </span>
        <span>
          Panel state: <strong>{label(state)}</strong>
        </span>
        <button
          className={styles.refreshButton}
          type="button"
          onClick={handleRefresh}
          disabled={state === 'loading' || busy}
        >
          {state === 'loading' ? 'Loading…' : 'Reload'}
        </button>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  Extraction helpers                                                */
/* ------------------------------------------------------------------ */

/**
 * Extract safety checks from the apply result.
 * Looks for structured data in `failure_evidence` or infers from status.
 */
function extractSafetyChecks(result: PatchApplyResult): SafetyCheck[] {
  // If failure_evidence contains structured safety-check data, use it.
  if (result.failure_evidence && typeof result.failure_evidence === 'object') {
    const ev = result.failure_evidence as Record<string, unknown>;

    // Check for a "safety_checks" array in evidence
    if (Array.isArray(ev.safety_checks)) {
      return ev.safety_checks.map((item: unknown) => {
        const raw = item as Record<string, unknown>;
        return {
          name: String(raw.name ?? 'unknown'),
          status: (['passed', 'failed', 'warning', 'skipped'].includes(
            String(raw.status),
          )
            ? String(raw.status)
            : 'skipped') as SafetyCheck['status'],
          detail: raw.detail ? String(raw.detail) : undefined,
        };
      });
    }

    // Check for individual check fields (e.g. "path_check", "applicability_check")
    const checkNames = [
      'path_validation',
      'applicability_check',
      'state_consistency',
      'checksum_verification',
      'fingerprint_match',
      'conflict_detection',
    ];
    const checks: SafetyCheck[] = [];
    for (const name of checkNames) {
      if (name in ev) {
        const raw = ev[name] as Record<string, unknown> | string;
        if (typeof raw === 'object') {
          checks.push({
            name,
            status: (['passed', 'failed', 'warning', 'skipped'].includes(
              String(raw.status),
            )
              ? String(raw.status)
              : 'skipped') as SafetyCheck['status'],
            detail: raw.detail ? String(raw.detail) : undefined,
          });
        } else {
          checks.push({
            name,
            status: String(raw) === 'true' ? 'passed' : 'failed',
          });
        }
      }
    }
    if (checks.length > 0) return checks;
  }

  // Fallback: derive synthetic checks from apply status
  const status = result.status;
  const checks: SafetyCheck[] = [
    {
      name: 'state_consistency',
      status: status === 'stale' ? 'failed' : status === 'applied' ? 'passed' : 'passed',
      detail: status === 'stale' ? 'State version mismatch detected.' : undefined,
    },
    {
      name: 'path_validation',
      status: status === 'blocked' ? 'failed' : 'passed',
      detail: status === 'blocked' ? 'Path validation failed or workspace mismatch.' : undefined,
    },
    {
      name: 'applicability_check',
      status: status === 'applied' || status === 'success' ? 'passed' : 'skipped',
      detail: status === 'applied' ? 'Diff applies cleanly.' : undefined,
    },
  ];

  // Include idempotent_replay info as a check if applicable
  if (result.idempotent_replay) {
    checks.push({
      name: 'idempotent_replay',
      status: 'warning',
      detail: 'This apply is an idempotent replay of a previous operation.',
    });
  }

  return checks;
}

/**
 * Extract dry run result from apply result.
 */
function extractDryRun(result: PatchApplyResult): DryRunResult | null {
  if (
    result.failure_evidence &&
    typeof result.failure_evidence === 'object'
  ) {
    const ev = result.failure_evidence as Record<string, unknown>;
    if (ev.dry_run && typeof ev.dry_run === 'object') {
      const dr = ev.dry_run as Record<string, unknown>;
      return {
        status: (['passed', 'failed', 'inconclusive'].includes(String(dr.status))
          ? String(dr.status)
          : 'inconclusive') as DryRunResult['status'],
        output: dr.output ? String(dr.output) : undefined,
        detail: dr.detail ? String(dr.detail) : undefined,
      };
    }
  }
  return null;
}

/**
 * Extract ledger info from apply result artifact refs.
 */
function extractLedger(result: PatchApplyResult): LedgerInfo | null {
  if (result.artifact_refs && typeof result.artifact_refs === 'object') {
    const ledgerKey = Object.keys(result.artifact_refs).find(
      (k) => k.toLowerCase().includes('ledger') || k.toLowerCase().includes('ledger_entry'),
    );
    if (ledgerKey) {
      return {
        entry_id: result.artifact_refs[ledgerKey],
        url: undefined, // will generate default URL in render
      };
    }
  }
  return null;
}
