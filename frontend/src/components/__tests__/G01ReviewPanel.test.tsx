import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiClientError } from '@/api/client';
import { decideG01, getProductionPreflight } from '@/api/preflights';
import { createAuthoritativeRun, startAuthoritativeRun } from '@/api/runs';
import { G01ReviewPanel } from '@/components/G01ReviewPanel';
import type { ProductionPreflight } from '@/types/preflight';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/api/preflights', () => ({ decideG01: vi.fn(), getProductionPreflight: vi.fn() }));
vi.mock('@/api/runs', () => ({ createAuthoritativeRun: vi.fn(), startAuthoritativeRun: vi.fn() }));
vi.mock('@/hooks/usePreflightEvents', () => ({ usePreflightEvents: () => ({ status: 'open', lastEventId: 7 }) }));

function fixture(overrides: Partial<ProductionPreflight['snapshot']> = {}): ProductionPreflight {
  return { snapshot: { preflight_id: 'preflight-1', gate_id: 'G01', gate_version: 's1-g01-v1', state_version: 3, status: 'passed_with_warnings', approval_status: 'pending', created_at: '2026-07-17T10:00:00Z', expires_at: '2026-07-17T11:00:00Z', input_checksum: 'sha256:input-with-a-very-long-value-for-layout-checking', artifact_set_checksum: 'sha256:evidence-with-a-very-long-value-for-layout-checking', target_angular_family: '21.x', migration_mode: 'strict-functional-parity', source_path: 'C:/external/source', target_parent_path: 'C:/external/target', generated_output_name: 'angular-21', resolved_output_root: 'C:/external/target/angular-21', platform_repository_root: 'C:/platform', target_output_path: 'C:/external/target/angular-21', target_reservation_id: 'reservation-1', blockers: [], warnings: ['NPM_REGISTRY_NOT_CONFIGURED', 'WORKSPACE_TOPOLOGY_UNKNOWN'], artifacts: { 'preflight_result.json': { artifact_id: 'artifact-1', checksum: 'sha256:artifact', relative_path: '00_job_setup/preflight_result.json' } }, decision_history: [], ...overrides } };
}

describe('G01ReviewPanel', () => {
  beforeEach(() => { vi.mocked(decideG01).mockReset(); vi.mocked(getProductionPreflight).mockReset(); vi.mocked(createAuthoritativeRun).mockReset(); vi.mocked(startAuthoritativeRun).mockReset(); push.mockReset(); });

  it('presents live preflight evidence, warning badges, and the backend artifact link', () => {
    render(<G01ReviewPanel preflight={fixture()} />);
    expect(screen.getByRole('heading', { name: 'G01 production preflight' })).toBeInTheDocument();
    expect(screen.getByText('NPM_REGISTRY_NOT_CONFIGURED')).toBeInTheDocument();
    expect(screen.getByText('WORKSPACE_TOPOLOGY_UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText('sha256:input-with-a-very-long-value-for-layout-checking')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open evidence' })).toHaveAttribute('href', 'http://127.0.0.1:8000/api/v1/artifacts/artifact-1');
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeDisabled();
  });

  it('records G01 approval with the current evidence and enables the authoritative-run action', async () => {
    vi.mocked(decideG01).mockResolvedValue({ decision_id: 'decision-1', preflight_id: 'preflight-1', gate_id: 'G01', decision: 'approved_with_comment', actor: 'control-tower', comment: 'ready', decided_at: '2026-07-17T10:05:00Z', input_checksum: 'sha256:input', artifact_set_checksum: 'sha256:evidence', state_version: 4, idempotent_replay: false });
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.change(screen.getByLabelText(/reviewer comment/i), { target: { value: 'ready' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve G01' }));
    await waitFor(() => expect(decideG01).toHaveBeenCalledWith('preflight-1', expect.objectContaining({ decision: 'approved_with_comment', comment: 'ready', input_checksum: expect.stringContaining('sha256:input') })));
    expect(await screen.findByText(/G01 approved with comment/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create and start authoritative run' })).toBeEnabled();
  });

  it('keeps backend failure details visible and offers an evidence refresh', async () => {
    vi.mocked(decideG01).mockRejectedValue(new ApiClientError('Backend request failed', 409, 'POST', '/g01', '{error_code:STALE_EVIDENCE}'));
    render(<G01ReviewPanel preflight={fixture()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reject G01' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('G01 decision could not be recorded');
    expect(alert).toHaveTextContent('STALE_EVIDENCE');
    expect(screen.getByRole('button', { name: 'Refresh G01 evidence' })).toBeEnabled();
  });
});
