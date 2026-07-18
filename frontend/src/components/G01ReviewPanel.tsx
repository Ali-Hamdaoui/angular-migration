'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiClientError, getBackendBaseUrl } from '@/api/client';
import { decideG01, getProductionPreflight } from '@/api/preflights';
import { createAuthoritativeRun, startAuthoritativeRun } from '@/api/runs';
import { usePreflightEvents } from '@/hooks/usePreflightEvents';
import type { G01Decision, ProductionPreflight } from '@/types/preflight';
import styles from './G01ReviewPanel.module.css';

type Notice = { tone: 'success' | 'error'; title: string; detail?: string };

function label(value: string) { return value.replaceAll('_', ' '); }

function detailFor(error: unknown, fallback: string): Notice {
  if (error instanceof ApiClientError) return { tone: 'error', title: fallback, detail: error.responseBody || error.message };
  return { tone: 'error', title: fallback, detail: error instanceof Error ? error.message : undefined };
}

function purposeFor(name: string) {
  if (name.includes('result')) return 'Authoritative preflight result';
  if (name.includes('environment')) return 'Environment capability evidence';
  if (name.includes('analysis')) return 'Source analysis evidence';
  return 'Preflight evidence';
}

export function G01ReviewPanel({ preflight, actor = 'control-tower' }: { preflight: ProductionPreflight; actor?: string }) {
  const router = useRouter();
  const [current, setCurrent] = useState(preflight);
  const [comment, setComment] = useState('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<G01Decision | null>(null);
  const [startingRun, setStartingRun] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try { setCurrent(await getProductionPreflight(preflight.snapshot.preflight_id)); }
    catch (error) { setNotice(detailFor(error, 'Unable to refresh G01 evidence.')); }
    finally { setRefreshing(false); }
  }, [preflight.snapshot.preflight_id]);
  const stream = usePreflightEvents(preflight.snapshot.preflight_id, refresh);
  const { snapshot } = current;
  const canDecide = !['blocked', 'expired', 'stale'].includes(snapshot.status);
  const canStart = ['approved', 'approved_with_comment'].includes(snapshot.approval_status);
  const latestDecision = snapshot.decision_history.at(-1);
  const startReason = canStart ? 'G01 is approved. Starting creates the authoritative, backend-owned run.' : 'Approve G01 before an authoritative run can be created.';

  async function submit(decision: G01Decision) {
    setBusy(decision); setNotice(null);
    try {
      const result = await decideG01(snapshot.preflight_id, { gate_id: snapshot.gate_id, decision, expected_state_version: snapshot.state_version, input_checksum: snapshot.input_checksum, artifact_set_checksum: snapshot.artifact_set_checksum, idempotency_key: `g01-${snapshot.preflight_id}-${decision}`, actor, comment: comment || null });
      setCurrent((value) => ({ ...value, snapshot: { ...value.snapshot, approval_status: result.decision, decision_history: [...value.snapshot.decision_history, result] } }));
      setNotice({ tone: 'success', title: `G01 ${label(result.decision)}${result.idempotent_replay ? ' (replayed)' : ''}.` });
    } catch (error) { setNotice(detailFor(error, 'G01 decision could not be recorded. Refresh evidence and retry.')); }
    finally { setBusy(null); }
  }

  async function handleStartAuthoritativeRun() {
    setStartingRun(true); setNotice(null);
    try {
      const created = await createAuthoritativeRun({ preflight_id: snapshot.preflight_id, input_checksum: snapshot.input_checksum, artifact_set_checksum: snapshot.artifact_set_checksum, idempotency_key: `run-create-${snapshot.preflight_id}`, actor, client_constraints: { preserve_ui: true, preserve_behavior: true, preserve_business_logic: true, preserve_api_contracts: true, preserve_authentication_authorization: true, allow_optional_modernization: false }, pricing_snapshot: {} });
      const started = await startAuthoritativeRun(created.run_id, { expected_state_version: created.state_version, idempotency_key: `run-start-${created.run_id}`, actor });
      router.push(`/migrations/${started.run_id}`);
    } catch (error) { setNotice(detailFor(error, 'The authoritative run could not be started.')); }
    finally { setStartingRun(false); }
  }

  return <section className={styles.page} aria-label={'G01 production preflight'}>
    <header className={styles.header}>
      <div><p className={styles.brand}>Control tower</p><h1>G01 production preflight</h1><p className={styles.description}>Review the authoritative evidence before creating an external, run-owned migration workspace.</p></div>
      <div className={styles.headerStatus}><span className={`${styles.connection} ${styles[`connection_${stream.status}`]}`}><i />{label(stream.status)}</span><span className={`${styles.badge} ${styles[`status_${snapshot.status}`]}`}>{label(snapshot.status)}</span></div>
    </header>

    <div className={styles.layout}>
      <div className={styles.primary}>
        <section className={styles.summaryCard} aria-labelledby={'summary-title'}>
          <div className={styles.cardHeading}><div><p className={styles.kicker}>Gate summary</p><h2 id={'summary-title'}>{snapshot.gate_id} · production readiness</h2></div><span className={`${styles.badge} ${styles[`approval_${snapshot.approval_status}`]}`}>{label(snapshot.approval_status)}</span></div>
          <dl className={styles.metrics}>
            <div><dt>Gate version</dt><dd>{snapshot.gate_version}</dd></div><div><dt>Warnings</dt><dd>{snapshot.warnings.length}</dd></div><div><dt>Evidence</dt><dd>{Object.keys(snapshot.artifacts).length} artifacts</dd></div><div><dt>State version</dt><dd>{snapshot.state_version}</dd></div>
          </dl>
          <dl className={styles.checksums}><div><dt>Input checksum</dt><dd><code>{snapshot.input_checksum}</code></dd></div><div><dt>Evidence checksum</dt><dd><code>{snapshot.artifact_set_checksum}</code></dd></div></dl>
        </section>

        <section className={styles.workspaceCard} aria-labelledby={'workspace-title'}><p className={styles.kicker}>Migration workspace</p><h2 id={'workspace-title'}>Source and target boundary</h2><div className={styles.pathRow}><span>Source · read-only</span><code>{snapshot.source_path}</code></div><div className={styles.pathRow}><span>Target · reserved output</span><code>{snapshot.target_output_path}</code></div></section>

        {snapshot.blockers.length > 0 || snapshot.warnings.length > 0 ? <section className={styles.attention} aria-labelledby={'attention-title'}><div className={styles.cardHeading}><div><p className={styles.kicker}>Review required</p><h2 id={'attention-title'}>Preflight findings</h2></div></div>{snapshot.blockers.length > 0 ? <div className={styles.findingGroup}><h3>Blockers</h3><div className={styles.findings}>{snapshot.blockers.map((item) => <span className={styles.blocker} key={item}>{item}</span>)}</div></div> : null}{snapshot.warnings.length > 0 ? <div className={styles.findingGroup}><h3>Warnings</h3><div className={styles.findings}>{snapshot.warnings.map((item) => <span className={styles.warning} key={item}>{item}</span>)}</div></div> : null}</section> : null}

        <section className={styles.evidenceCard} aria-labelledby={'evidence-title'}><div className={styles.cardHeading}><div><p className={styles.kicker}>Immutable evidence</p><h2 id={'evidence-title'}>G01 artifacts</h2></div><span>{Object.keys(snapshot.artifacts).length} available</span></div><ul className={styles.artifactList}>{Object.entries(snapshot.artifacts).map(([name, artifact]) => <li key={name}><div><strong>{name}</strong><span>{purposeFor(name)}</span><code>{artifact.relative_path}</code></div><div className={styles.artifactAction}><code>{artifact.checksum}</code><a href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}`}>Open evidence</a></div></li>)}</ul></section>
      </div>

      <aside className={styles.sidebar}>
        <section className={styles.decisionCard} aria-labelledby={'decision-title'}><p className={styles.kicker}>Approval gate</p><h2 id={'decision-title'}>Reviewer decision</h2><p className={styles.note}>{canDecide ? 'Record a decision against this exact evidence set.' : 'This preflight cannot be decided until its status is resolved.'}</p><label className={styles.commentLabel} htmlFor={'g01-comment'}>Reviewer comment <span>Optional for approval; include rationale for requested changes.</span></label><textarea id={'g01-comment'} value={comment} onChange={(event) => setComment(event.target.value)} rows={5} placeholder={'Add a review note'} disabled={busy !== null || startingRun} /><div className={styles.actions}><button className={styles.approve} type={'button'} disabled={busy !== null || startingRun || !canDecide} onClick={() => submit(comment ? 'approved_with_comment' : 'approved')}>{busy === 'approved' || busy === 'approved_with_comment' ? 'Recording approval…' : 'Approve G01'}</button><button className={styles.modify} type={'button'} disabled={busy !== null || startingRun || !canDecide} onClick={() => submit('modification_requested')}>{busy === 'modification_requested' ? 'Recording…' : 'Request modification'}</button><button className={styles.reject} type={'button'} disabled={busy !== null || startingRun || !canDecide} onClick={() => submit('rejected')}>{busy === 'rejected' ? 'Recording…' : 'Reject G01'}</button></div>{latestDecision ? <p className={styles.decisionHistory}>Latest decision: <strong>{label(latestDecision.decision)}</strong>{latestDecision.comment ? ` — ${latestDecision.comment}` : ''}</p> : null}</section>

        <section className={styles.runCard} aria-labelledby={'run-title'}><p className={styles.kicker}>Authoritative run</p><h2 id={'run-title'}>Start migration</h2><p className={styles.note}>{startReason}</p><button className={styles.startRun} type={'button'} disabled={!canStart || startingRun || busy !== null} onClick={handleStartAuthoritativeRun}>{startingRun ? 'Creating authoritative run…' : 'Create and start authoritative run'}</button></section>

        {notice ? <section className={`${styles.notice} ${notice.tone === 'error' ? styles.noticeError : styles.noticeSuccess}`} role={notice.tone === 'error' ? 'alert' : 'status'}><strong>{notice.title}</strong>{notice.detail ? <p>{notice.detail}</p> : null}{notice.tone === 'error' ? <button type={'button'} onClick={() => void refresh()} disabled={refreshing}>{refreshing ? 'Refreshing evidence…' : 'Refresh G01 evidence'}</button> : null}</section> : null}
      </aside>
    </div>
    <footer className={styles.footer}><span>Gate {snapshot.gate_id} · {snapshot.gate_version}</span><span>Event stream: {label(stream.status)}{stream.lastEventId !== null ? ` · event ${stream.lastEventId}` : ''}</span><button type={'button'} onClick={() => void refresh()} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh evidence'}</button></footer>
  </section>;
}
