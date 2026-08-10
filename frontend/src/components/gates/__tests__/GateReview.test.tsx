import { fireEvent, render, screen, within } from '@testing-library/react';
import { presentStatus } from '@/presentation/status';
import { GateReview, type GateReviewModel } from '@/components/gates/GateReview';
import { GateDecisionPanel } from '@/components/gates/GateDecisionPanel';

function model(overrides: Partial<GateReviewModel> = {}): GateReviewModel {
  return {
    gateId: 'G01',
    status: 'pending',
    title: 'G01 production readiness',
    purpose: 'Confirm the source boundary and reserved target are safe.',
    requiredDecision: 'Decide whether this evidence may create a run.',
    verified: ['The source is read-only.', 'The target output is reserved.'],
    blockers: ['SOURCE_PATH_NOT_FOUND'],
    warnings: ['WORKSPACE_TOPOLOGY_UNKNOWN'],
    evidenceGroups: [{
      title: 'Production readiness result',
      summary: 'Available evidence',
      artifactIds: ['artifact-1'],
      status: presentStatus('AVAILABLE'),
    }],
    technicalBindings: [{ label: 'Input checksum', value: 'sha256:input' }],
    ...overrides,
  };
}

function expectBefore(first: HTMLElement, second: HTMLElement) {
  expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}

describe('GateReview', () => {
  it('renders the governed reading order exactly', () => {
    render(
      <GateReview
        model={model()}
        artifactLinks={{ 'artifact-1': { href: '/artifacts/artifact-1', label: 'Open evidence' } }}
        decisionPanel={<section><h2>Reviewer controls</h2><button type="button">Approve G01</button></section>}
      />,
    );

    const ordered = [
      screen.getByRole('heading', { name: 'G01 production readiness' }),
      screen.getByRole('heading', { name: 'Why this review exists' }),
      screen.getByRole('heading', { name: 'Decision required' }),
      screen.getByRole('heading', { name: 'Verified facts' }),
      screen.getByRole('heading', { name: 'Blockers' }),
      screen.getByRole('heading', { name: 'Warnings' }),
      screen.getByRole('heading', { name: 'Evidence' }),
      screen.getByRole('heading', { name: 'Reviewer controls' }),
      screen.getByText('Technical details'),
    ];
    ordered.slice(0, -1).forEach((item, index) => expectBefore(item, ordered[index + 1]));
  });

  it('renders supplied decision controls only for a pending gate', () => {
    render(<GateReview model={model()} decisionPanel={<button type="button">Approve G01</button>} />);
    expect(screen.getByRole('button', { name: 'Approve G01' })).toBeInTheDocument();
  });

  it.each([
    ['approved', 'Approved'],
    ['rejected', 'Rejected'],
    ['modification_requested', 'Modification requested'],
    ['stale', 'Stale'],
    ['expired', 'Expired'],
  ] as const)('renders the %s terminal outcome and discards supplied controls', (status, label) => {
    render(
      <GateReview
        model={model({
          status,
          outcome: { label, consequence: `${label} consequence.` },
        })}
        decisionPanel={<button type="button">Approve</button>}
      />,
    );

    expect(screen.getByRole('heading', { name: label })).toBeInTheDocument();
    expect(screen.getByText(`${label} consequence.`)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Decision outcome' })).toBeInTheDocument();
  });

  it('generates distinct reusable label targets for multiple review and decision instances', () => {
    const decisionProps = {
      comment: '',
      onCommentChange: vi.fn(),
      onApprove: vi.fn(),
      onRequestModification: vi.fn(),
      onReject: vi.fn(),
      busy: false,
    };
    render(<>
      <GateReview model={model({ title: 'First review' })} />
      <GateReview model={model({ title: 'Second review' })} />
      <GateDecisionPanel {...decisionProps} />
      <GateDecisionPanel {...decisionProps} />
    </>);

    const textareas = screen.getAllByRole('textbox', { name: /Reviewer comment/ });
    expect(textareas[0]).not.toHaveAttribute('id', textareas[1].id);
    const reviews = screen.getAllByRole('article');
    expect(reviews[0]).not.toHaveAttribute('aria-labelledby', reviews[1].getAttribute('aria-labelledby'));
  });

  it('uses the native Technical details disclosure closed by default', () => {
    render(<GateReview model={model()} />);
    const summary = screen.getByText('Technical details');
    const details = summary.closest('details');
    expect(details).not.toHaveAttribute('open');
    expect(screen.getByText('sha256:input')).not.toBeVisible();

    fireEvent.click(summary);

    expect(details).toHaveAttribute('open');
    expect(screen.getByText('sha256:input')).toBeVisible();
  });

  it('renders human evidence titles, summaries, status, and caller-supplied artifact links', () => {
    render(
      <GateReview
        model={model()}
        artifactLinks={{ 'artifact-1': { href: '/api/v1/artifacts/artifact-1', label: 'Open production readiness result' } }}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Production readiness result' })).toBeInTheDocument();
    expect(screen.getByText('Available evidence')).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open production readiness result' })).toHaveAttribute('href', '/api/v1/artifacts/artifact-1');
  });

  it('states when an artifact is known but caller link metadata is unavailable', () => {
    render(<GateReview model={model()} />);
    expect(screen.getByText('Artifact link metadata is unavailable for this evidence group.')).toBeInTheDocument();
    const evidenceCard = screen.getByRole('heading', { name: 'Production readiness result' }).closest('section');
    expect(evidenceCard).not.toBeNull();
    expect(within(evidenceCard as HTMLElement).queryByRole('list')).not.toBeInTheDocument();
  });

  it('states explicitly when verified facts, findings, and evidence are unavailable', () => {
    render(<GateReview model={model({ verified: [], blockers: [], warnings: [], evidenceGroups: [] })} />);
    expect(screen.getByText('No verified facts are available for this review.')).toBeInTheDocument();
    expect(screen.getByText('No blockers were reported.')).toBeInTheDocument();
    expect(screen.getByText('No warnings were reported.')).toBeInTheDocument();
    expect(screen.getByText('No evidence groups are available for this review.')).toBeInTheDocument();
  });
});
