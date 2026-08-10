import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiClientError } from '@/api/client';
import { decideG01, getProductionPreflight } from '@/api/preflights';
import { createAuthoritativeRun, getAuthoritativeRunState, startAuthoritativeRun } from '@/api/runs';
import { G01ReviewPanel } from '@/components/G01ReviewPanel';
import type { G01DecisionResponse, ProductionPreflight } from '@/types/preflight';

const push = vi.fn();
let eventRefresh: (() => void) | null = null;

vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/api/preflights', () => ({ decideG01: vi.fn(), getProductionPreflight: vi.fn() }));
vi.mock('@/api/runs', () => ({ createAuthoritativeRun: vi.fn(), getAuthoritativeRunState: vi.fn(), startAuthoritativeRun: vi.fn() }));
vi.mock('@/hooks/usePreflightEvents', () => ({
  usePreflightEvents: (_preflightId: string, onEvent: () => void) => {
    eventRefresh = onEvent;
    return { status: 'open', lastEventId: 7 };
  },
}));

function fixture(overrides: Partial<ProductionPreflight['snapshot']> = {}): ProductionPreflight {
  return {
    snapshot: {
      preflight_id: 'preflight-1',
      gate_id: 'G01',
      gate_version: 's1-g01-v1',
      state_version: 3,
      status: 'passed_with_warnings',
      approval_status: 'pending',
      created_at: '2026-07-17T10:00:00Z',
      expires_at: '2099-07-17T11:00:00Z',
      input_checksum: 'sha256:input-with-a-very-long-value-for-layout-checking',
      artifact_set_checksum: 'sha256:evidence-with-a-very-long-value-for-layout-checking',
      target_angular_family: '21.x',
      migration_mode: 'strict-functional-parity',
      source_path: 'C:/external/source',
      target_parent_path: 'C:/external/target',
      generated_output_name: 'angular-21',
      resolved_output_root: 'C:/external/target/angular-21',
      platform_repository_root: 'C:/platform',
      target_output_path: 'C:/external/target/angular-21',
      target_reservation_id: 'reservation-1',
      blockers: [],
      warnings: ['NPM_REGISTRY_NOT_CONFIGURED', 'WORKSPACE_TOPOLOGY_UNKNOWN'],
      artifacts: {
        'preflight_result.json': {
          artifact_id: 'artifact/1',
          checksum: 'sha256:artifact',
          relative_path: '00_job_setup/preflight_result.json',
        },
        'preflight_request.json': {
          artifact_id: 'artifact/request',
          checksum: 'sha256:request',
          relative_path: '00_job_setup/preflight_request.json',
        },
        'environment_capability_summary.json': {
          artifact_id: 'artifact/environment',
          checksum: 'sha256:environment',
          relative_path: '00_job_setup/environment_capability_summary.json',
        },
        'path_safety_report.json': {
          artifact_id: 'artifact/path-safety',
          checksum: 'sha256:path-safety',
          relative_path: '00_job_setup/path_safety_report.json',
        },
        'eligibility_result.json': {
          artifact_id: 'artifact/eligibility',
          checksum: 'sha256:eligibility',
          relative_path: '00_job_setup/eligibility_result.json',
        },
      },
      decision_history: [],
      ...overrides,
    },
  };
}

function decision(overrides: Partial<G01DecisionResponse> = {}): G01DecisionResponse {
  return {
    decision_id: 'decision-1',
    preflight_id: 'preflight-1',
    gate_id: 'G01',
    decision: 'approved',
    actor: 'control-tower',
    comment: null,
    decided_at: '2026-07-17T10:05:00Z',
    input_checksum: 'sha256:input-with-a-very-long-value-for-layout-checking',
    artifact_set_checksum: 'sha256:evidence-with-a-very-long-value-for-layout-checking',
    state_version: 3,
    idempotent_replay: false,
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => { resolve = onResolve; reject = onReject; });
  return { promise, resolve, reject };
}

function expectNoDecisionButtons() {
  expect(screen.queryByRole('button', { name: 'Approve G01' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Request modification' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Reject G01' })).not.toBeInTheDocument();
}

function expectNoRunButton() {
  expect(screen.queryByRole('button', { name: 'Create and start authoritative run' })).not.toBeInTheDocument();
}

describe('G01ReviewPanel', () => {
  beforeEach(() => {
    vi.mocked(decideG01).mockReset();
    vi.mocked(getProductionPreflight).mockReset();
    vi.mocked(createAuthoritativeRun).mockReset();
    vi.mocked(getAuthoritativeRunState).mockReset();
    vi.mocked(startAuthoritativeRun).mockReset();
    window.localStorage.clear();
    push.mockReset();
    eventRefresh = null;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('presents the source/target boundary, exact findings, human artifact title/link, and collapsed checksums', () => {
    render(<G01ReviewPanel preflight={fixture({ blockers: ['SOURCE_PATH_NOT_FOUND'] })} />);

    expect(screen.getByRole('heading', { name: 'G01 production readiness' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByText('Source is read-only: C:/external/source')).toBeInTheDocument();
    expect(screen.getByText('Target is reserved output: C:/external/target/angular-21')).toBeInTheDocument();
    const blocker = screen.getByText('SOURCE_PATH_NOT_FOUND');
    const warning = screen.getByText('NPM_REGISTRY_NOT_CONFIGURED');
    expect(blocker.compareDocumentPosition(warning) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Production readiness result' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Production readiness result' })).toHaveAttribute(
      'href',
      'http://127.0.0.1:8000/api/v1/artifacts/artifact%2F1',
    );
    expect(screen.getByText('sha256:input-with-a-very-long-value-for-layout-checking')).not.toBeVisible();
    expect(screen.getByText('sha256:evidence-with-a-very-long-value-for-layout-checking')).not.toBeVisible();
  });

  it('sends approved with a null comment when the reviewer comment is empty', async () => {
    vi.mocked(decideG01).mockResolvedValue(decision());
    render(<G01ReviewPanel preflight={fixture()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));

    await waitFor(() => expect(decideG01).toHaveBeenCalledWith('preflight-1', {
      gate_id: 'G01',
      decision: 'approved',
      expected_state_version: 3,
      input_checksum: 'sha256:input-with-a-very-long-value-for-layout-checking',
      artifact_set_checksum: 'sha256:evidence-with-a-very-long-value-for-layout-checking',
      idempotency_key: 'g01-preflight-1-approved',
      actor: 'control-tower',
      comment: null,
    }));
  });

  it('sends approved_with_comment and preserves a nonempty reviewer comment exactly', async () => {
    vi.mocked(decideG01).mockResolvedValue(decision({ decision: 'approved_with_comment', comment: ' ready ' }));
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.change(screen.getByLabelText('Reviewer comment'), { target: { value: ' ready ' } });

    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));

    await waitFor(() => expect(decideG01).toHaveBeenCalledWith('preflight-1', expect.objectContaining({
      decision: 'approved_with_comment',
      comment: ' ready ',
    })));
  });

  it('keeps modification and rejection legal while a blocked pending review disables approval', () => {
    render(<G01ReviewPanel preflight={fixture({ status: 'blocked', blockers: ['SOURCE_PATH_NOT_FOUND'] })} />);
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Request modification' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Reject G01' })).toBeEnabled();
  });

  it('renders an initially approved gate as terminal with run creation enabled', () => {
    render(<G01ReviewPanel preflight={fixture({ approval_status: 'approved' })} />);
    expect(screen.getByRole('heading', { name: 'Approved' })).toBeInTheDocument();
    expectNoDecisionButtons();
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeEnabled();
  });

  it('renders a successful approval response as terminal and retains its exact outcome comment', async () => {
    vi.mocked(decideG01).mockResolvedValue(decision({ decision: 'approved_with_comment', comment: 'Evidence accepted.' }));
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.change(screen.getByLabelText('Reviewer comment'), { target: { value: 'Evidence accepted.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));

    expect(await screen.findByRole('heading', { name: 'Approved with comment' })).toBeInTheDocument();
    expect(screen.getByText('Evidence accepted.')).toBeInTheDocument();
    expectNoDecisionButtons();
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeEnabled();
  });

  it.each([
    [{ approval_status: 'rejected' }, 'Rejected'],
    [{ approval_status: 'modification_requested' }, 'Modification requested'],
    [{ approval_status: 'stale' }, 'Stale'],
    [{ status: 'stale' }, 'Stale'],
    [{ approval_status: 'expired' }, 'Expired'],
    [{ status: 'expired' }, 'Expired'],
    [{ expires_at: '2020-01-01T00:00:00Z' }, 'Expired'],
  ] as const)('renders %o as terminal %s with no decision or run authorization', (overrides, outcome) => {
    render(<G01ReviewPanel preflight={fixture(overrides)} />);
    expect(screen.getByRole('heading', { name: outcome })).toBeInTheDocument();
    expectNoDecisionButtons();
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeDisabled();
  });

  it('fails closed for an unrecognized or inconsistent authoritative state', () => {
    render(<G01ReviewPanel preflight={fixture({ approval_status: 'unexpected' as never })} />);
    expect(screen.getByText('Unknown status')).toBeInTheDocument();
    expectNoDecisionButtons();
    expectNoRunButton();
  });

  it('fails closed when authoritative evidence is bound to a gate other than G01', () => {
    render(<G01ReviewPanel preflight={fixture({ gate_id: 'G02' })} />);
    expect(screen.getByText('Unknown status')).toBeInTheDocument();
    expectNoDecisionButtons();
    expectNoRunButton();
  });

  it('becomes terminal at expires_at and guards a decision clicked after expiry', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-17T10:00:00Z'));
    render(<G01ReviewPanel preflight={fixture({ expires_at: '2026-07-17T10:00:01Z' })} />);
    const approve = screen.getByRole('button', { name: 'Approve G01' });

    vi.setSystemTime(new Date('2026-07-17T10:00:02Z'));
    fireEvent.click(approve);
    expect(decideG01).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'Expired' })).toBeInTheDocument();
    expectNoDecisionButtons();
  });

  it('turns an approved gate terminal at expires_at and disables run creation', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-17T10:00:00Z'));
    render(<G01ReviewPanel preflight={fixture({
      approval_status: 'approved',
      expires_at: '2026-07-17T10:00:01Z',
    })} />);
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeEnabled();

    act(() => { vi.advanceTimersByTime(1_000); });

    expect(screen.getByRole('heading', { name: 'Expired' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeDisabled();
  });

  it('invalidates stale approved controls immediately when run creation is clicked after expiry', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-17T10:00:00Z'));
    render(<G01ReviewPanel preflight={fixture({
      approval_status: 'approved',
      expires_at: '2026-07-17T10:00:01Z',
    })} />);
    const createRun = screen.getByRole('button', { name: 'Create and start authoritative run' });

    vi.setSystemTime(new Date('2026-07-17T10:00:02Z'));
    fireEvent.click(createRun);

    expect(createAuthoritativeRun).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'Expired' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeDisabled();
  });

  it('reschedules clamped timers until a long-horizon preflight expires', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-17T10:00:00Z'));
    render(<G01ReviewPanel preflight={fixture({ expires_at: '2026-09-17T10:00:00Z' })} />);

    act(() => { vi.advanceTimersByTime(2_147_483_647); });
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
    act(() => { vi.advanceTimersByTime(2_147_483_647); });
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
    act(() => { vi.runOnlyPendingTimers(); });

    expect(screen.getByRole('heading', { name: 'Expired' })).toBeInTheDocument();
    expectNoDecisionButtons();
  });

  it('fails closed when expires_at is malformed', () => {
    render(<G01ReviewPanel preflight={fixture({ expires_at: 'not-a-timestamp' })} />);
    expect(screen.getByText('Unknown status')).toBeInTheDocument();
    expectNoDecisionButtons();
    expectNoRunButton();
  });

  it.each([
    ['empty preflight ID', { preflight_id: '' }],
    ['empty gate version', { gate_version: ' ' }],
    ['empty input checksum', { input_checksum: '' }],
    ['empty artifact-set checksum', { artifact_set_checksum: ' ' }],
    ['empty source path', { source_path: '' }],
    ['empty target path', { target_output_path: '' }],
    ['missing reservation', { target_reservation_id: null }],
    ['invalid state version', { state_version: 0 }],
    ['invalid creation timestamp', { created_at: 'not-a-timestamp' }],
  ] as const)('fails closed for a runtime-invalid G01 package: %s', (_label, overrides) => {
    render(<G01ReviewPanel preflight={fixture(overrides)} />);
    expect(screen.getByText('Unknown status')).toBeInTheDocument();
    expectNoDecisionButtons();
    expectNoRunButton();
  });

  it.each([
    ['missing required artifact', (() => {
      const artifacts = { ...fixture().snapshot.artifacts };
      delete artifacts['path_safety_report.json'];
      return artifacts;
    })()],
    ['malformed required artifact', {
      ...fixture().snapshot.artifacts,
      'eligibility_result.json': {
        artifact_id: '',
        checksum: 'sha256:eligibility',
        relative_path: '00_job_setup/eligibility_result.json',
      },
    }],
  ] as const)('fails closed for %s', (_label, artifacts) => {
    render(<G01ReviewPanel preflight={fixture({ artifacts })} />);
    expect(screen.getByText('Unknown status')).toBeInTheDocument();
    expectNoDecisionButtons();
    expectNoRunButton();
  });

  it('does not authorize run creation for an approved malformed package', () => {
    render(<G01ReviewPanel preflight={fixture({ approval_status: 'approved', target_reservation_id: '' })} />);
    expect(screen.getByText('Unknown status')).toBeInTheDocument();
    expectNoDecisionButtons();
    expectNoRunButton();
  });

  it('does not treat legacy layout metadata as an authorization binding', () => {
    render(<G01ReviewPanel preflight={fixture({
      target_parent_path: '',
      generated_output_name: '',
      resolved_output_root: '',
    })} />);
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
  });

  it('renders unavailable instead of crashing for malformed decision history', () => {
    render(<G01ReviewPanel preflight={fixture({ decision_history: null as never })} />);
    expect(screen.getByText('Unknown status')).toBeInTheDocument();
    expectNoDecisionButtons();
    expectNoRunButton();
  });

  it('rejects an invalid refresh and later accepts a valid lower-version recovery', async () => {
    vi.mocked(getProductionPreflight)
      .mockResolvedValueOnce(fixture({ state_version: 20, target_reservation_id: '' }))
      .mockResolvedValueOnce(fixture({ state_version: 4, warnings: ['VALID_RECOVERY'] }));
    render(<G01ReviewPanel preflight={fixture()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }));
    expect(await screen.findByText('Refreshed G01 evidence was not authoritative.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Reload G01 evidence' }));
    expect(await screen.findByText('VALID_RECOVERY')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
  });

  it('rejects refreshed evidence bound to another preflight', async () => {
    vi.mocked(getProductionPreflight).mockResolvedValue(fixture({ preflight_id: 'different-preflight', state_version: 20 }));
    render(<G01ReviewPanel preflight={fixture()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }));

    expect(await screen.findByText('Refreshed G01 evidence was not authoritative.')).toBeInTheDocument();
    expect(screen.getByText('preflight-1')).toBeInTheDocument();
    expect(screen.queryByText('different-preflight')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
  });

  it('ignores a successful response for a decision other than the submitted decision', async () => {
    vi.mocked(decideG01).mockResolvedValue(decision({ decision: 'rejected' }));
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));

    expect(await screen.findByText('A newer G01 state superseded this decision response.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
    expect(screen.queryByRole('heading', { name: 'Rejected' })).not.toBeInTheDocument();
  });

  it('rejects a decision response that would construct a malformed evidence package', async () => {
    vi.mocked(decideG01).mockResolvedValue(decision({ actor: '', decided_at: 'invalid-time' }));
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));

    expect(await screen.findByText('A newer G01 state superseded this decision response.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
    expect(screen.queryByText(/^G01 approved/i)).not.toBeInTheDocument();
  });

  it('automatically reloads a 409, preserves the comment, announces changed evidence, and never reports success', async () => {
    vi.mocked(decideG01).mockRejectedValue(new ApiClientError('Backend request failed', 409, 'POST', '/g01', '{"error_code":"STALE_EVIDENCE"}'));
    vi.mocked(getProductionPreflight).mockResolvedValue(fixture({ state_version: 4, warnings: ['UPDATED_WARNING'] }));
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.change(screen.getByLabelText('Reviewer comment'), { target: { value: 'Keep this note' } });

    fireEvent.click(screen.getByRole('button', { name: 'Reject G01' }));

    await waitFor(() => expect(getProductionPreflight).toHaveBeenCalledWith('preflight-1'));
    expect(await screen.findByText('Evidence changed. Review the updated evidence and decide again.')).toBeInTheDocument();
    expect(screen.getByText('UPDATED_WARNING')).toBeInTheDocument();
    expect(screen.getByLabelText('Reviewer comment')).toHaveValue('Keep this note');
    expect(screen.queryByText(/G01 rejected/i)).not.toBeInTheDocument();
  });

  it('fails closed after a 409 reload failure and restores authority only after a successful reload', async () => {
    vi.mocked(decideG01).mockRejectedValue(new ApiClientError('Backend request failed', 409, 'POST', '/g01', 'stale'));
    vi.mocked(getProductionPreflight)
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce(fixture({ state_version: 4, warnings: ['RECOVERED_WARNING'] }));
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.change(screen.getByLabelText('Reviewer comment'), { target: { value: 'Keep this note' } });
    fireEvent.click(screen.getByRole('button', { name: 'Reject G01' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Updated G01 evidence could not be loaded');
    expectNoDecisionButtons();
    expectNoRunButton();

    fireEvent.click(screen.getByRole('button', { name: 'Reload G01 evidence' }));

    expect(await screen.findByText('RECOVERED_WARNING')).toBeInTheDocument();
    expect(screen.getByLabelText('Reviewer comment')).toHaveValue('Keep this note');
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled();
    expect(screen.queryByText('Updated G01 evidence could not be loaded.')).not.toBeInTheDocument();
  });

  it('ignores a late decision result after newer terminal evidence already contains it', async () => {
    const post = deferred<G01DecisionResponse>();
    const staleResult = decision({ decision_id: 'decision-stale', state_version: 4 });
    const newestDecision = decision({
      decision_id: 'decision-newest',
      decision: 'rejected',
      state_version: 5,
      comment: 'Newest rejection.',
    });
    vi.mocked(decideG01).mockReturnValue(post.promise);
    vi.mocked(getProductionPreflight).mockResolvedValue(fixture({
      state_version: 5,
      approval_status: 'rejected',
      decision_history: [staleResult, newestDecision],
    }));
    render(<G01ReviewPanel preflight={fixture()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));
    eventRefresh?.();
    expect(await screen.findByRole('heading', { name: 'Rejected' })).toBeInTheDocument();

    await act(async () => { post.resolve(staleResult); });

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Rejected' })).toBeInTheDocument());
    expect(screen.getByText('Newest rejection.')).toBeInTheDocument();
    expect(screen.queryByText(/^G01 approved/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Technical details'));
    expect(screen.getByText('Decision history entries').closest('div')).toHaveTextContent('2');
  });

  it('does not hybridize a late decision result with newer bindings', async () => {
    const post = deferred<G01DecisionResponse>();
    vi.mocked(decideG01).mockReturnValue(post.promise);
    vi.mocked(getProductionPreflight).mockResolvedValue(fixture({
      state_version: 5,
      input_checksum: 'sha256:new-input',
      artifact_set_checksum: 'sha256:new-artifacts',
    }));
    render(<G01ReviewPanel preflight={fixture()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));
    eventRefresh?.();
    await waitFor(() => expect(getProductionPreflight).toHaveBeenCalledTimes(1));
    await act(async () => { post.resolve(decision({ state_version: 4 })); });

    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve G01' })).toBeEnabled());
    expect(screen.queryByRole('heading', { name: 'Approved' })).not.toBeInTheDocument();
    expect(screen.queryByText(/^G01 approved/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Technical details'));
    expect(screen.getByText('sha256:new-input')).toBeVisible();
    expect(screen.getByText('sha256:new-artifacts')).toBeVisible();
  });

  it('does not let an older refresh regress a newer terminal decision to pending', async () => {
    const refreshResult = deferred<ProductionPreflight>();
    vi.mocked(getProductionPreflight).mockReturnValue(refreshResult.promise);
    vi.mocked(decideG01).mockResolvedValue(decision({ state_version: 5 }));
    render(<G01ReviewPanel preflight={fixture()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence' }));
    await waitFor(() => expect(getProductionPreflight).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));
    expect(await screen.findByRole('heading', { name: 'Approved' })).toBeInTheDocument();

    refreshResult.resolve(fixture({ state_version: 4, approval_status: 'pending' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Approved' })).toBeInTheDocument());
    expectNoDecisionButtons();
  });

  it('uses the unchanged event hook callback to refresh this panel', async () => {
    vi.mocked(getProductionPreflight).mockResolvedValue(fixture({ state_version: 4 }));
    render(<G01ReviewPanel preflight={fixture()} />);
    expect(eventRefresh).not.toBeNull();
    eventRefresh?.();
    await waitFor(() => expect(getProductionPreflight).toHaveBeenCalledWith('preflight-1'));
  });

  it('reopens a persisted run when start reports an active-run conflict', async () => {
    vi.mocked(createAuthoritativeRun).mockResolvedValue({ run_id: 'new-run', state_version: 2 } as never);
    vi.mocked(startAuthoritativeRun).mockRejectedValue(new ApiClientError('active run', 409, 'POST', '/runs/new-run/start', '{"error_code":"ACTIVE_RUN_EXISTS"}'));
    vi.mocked(getAuthoritativeRunState).mockResolvedValue({ run_id: 'existing-run' } as never);
    window.localStorage.setItem('amfa.activeRunId', 'existing-run');
    render(<G01ReviewPanel preflight={fixture({ approval_status: 'approved' })} />);

    fireEvent.click(screen.getByRole('button', { name: 'Create and start authoritative run' }));

    await waitFor(() => expect(getAuthoritativeRunState).toHaveBeenCalledWith('existing-run'));
    expect(push).toHaveBeenCalledWith('/?run_id=existing-run');
  });

  it('keeps the exact create/start/storage/deep-link chain for a newly authorized run', async () => {
    vi.mocked(createAuthoritativeRun).mockResolvedValue({ run_id: 'created-run', state_version: 2 } as never);
    vi.mocked(startAuthoritativeRun).mockResolvedValue({ run_id: 'created-run', state_version: 3 } as never);
    render(<G01ReviewPanel preflight={fixture({ approval_status: 'approved' })} actor="operator" />);

    fireEvent.click(screen.getByRole('button', { name: 'Create and start authoritative run' }));

    await waitFor(() => expect(createAuthoritativeRun).toHaveBeenCalledWith({
      preflight_id: 'preflight-1',
      input_checksum: 'sha256:input-with-a-very-long-value-for-layout-checking',
      artifact_set_checksum: 'sha256:evidence-with-a-very-long-value-for-layout-checking',
      idempotency_key: 'run-create-preflight-1',
      actor: 'operator',
      client_constraints: {
        preserve_ui: true,
        preserve_behavior: true,
        preserve_business_logic: true,
        preserve_api_contracts: true,
        preserve_authentication_authorization: true,
        allow_optional_modernization: false,
      },
      pricing_snapshot: {},
    }));
    expect(startAuthoritativeRun).toHaveBeenCalledWith('created-run', {
      expected_state_version: 2,
      idempotency_key: 'run-start-created-run',
      actor: 'operator',
    });
    expect(window.localStorage.getItem('amfa.activeRunId')).toBe('created-run');
    expect(push).toHaveBeenCalledWith('/?run_id=created-run');
  });
});
