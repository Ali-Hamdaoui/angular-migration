# Journey Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Angular Migration Factory's subsystem-led frontend with the approved Journey Command Center: a clear four-destination, backend-authoritative operator workspace covering setup, G01-G12, evidence, diagnostics, and accessible assistant support.

**Architecture:** Keep the existing Next.js/React route boundaries, typed API clients, backend state machine, SSE recovery, and decision bindings. Add pure presentation adapters between authoritative data and UI, make `AuthoritativeRunDashboard` the single owner of run and optional transformation projections, and compose every screen from shared journey, status, gate, evidence, and progressive-disclosure primitives. Do not compare the run and transformation `state_version` counters because they are projection-local.

**Tech Stack:** Next.js, React, TypeScript, CSS Modules, Vitest, Testing Library, Playwright with installed Microsoft Edge, `lucide-react@1.31.0`

**Approved references:**

- Design specification: `docs/superpowers/specs/2026-08-09-journey-command-center-design.md`
- Selected visual target: `docs/superpowers/specs/assets/2026-08-09-journey-command-center/selected-journey-command-center.png`

## Global Constraints

- Preserve backend authority. The UI may explain or group explicit backend facts; it may not invent progress, permission, completion, evidence, recovery, or a gate.
- Preserve existing API requests, state-version checks, idempotency keys, checksums, workspace fingerprints, stale-decision handling, event ordering, duplicate suppression, event-gap recovery, and source read-only guarantees.
- Never compare `AuthoritativeRunStateDto.state_version` with `TransformationProjection.state_version`. Show a refresh mismatch only for a backend-reported event gap, stale binding, incompatible shared identifier, or failed refresh.
- Keep exactly four primary live-run destinations: Overview, Pipeline, Evidence, and Diagnostics. Transformation is part of Pipeline; Assistant is subordinate navigation.
- Use the G01-G12 names and meanings from the approved specification. In particular, G11 is **Repair validation acceptance** and G12 is **Stage-completion acceptance**.
- Show a gate action only when the exact backend package and required binding values are present. Terminal, stale, rejected, and expired gates are read-only.
- Do not add backend endpoints, commands, decisions, workflow states, or optimistic domain transitions.
- Use `lucide-react` for icons. Do not use text glyphs, emoji, gradients, glow effects, or external font dependencies.
- Minimum body text is 16 px, minimum pointer target is 44 x 44 px, status is never color-only, and all paths/checksums stay within their own wrapping or scrolling region.
- Preserve existing routes. Adapt `mock-*` runs to the same visual shell instead of retaining a competing design system.
- Run focused tests after every behavior change and the full frontend gates before completion. Never weaken a domain assertion merely to make the suite green.
- Before translating the selected mock in Tasks 3 and 6, use `product-design:image-to-code` and `build-web-apps:frontend-app-builder`; the visual direction is already selected, so do not generate a competing design. Use `build-web-apps:frontend-testing-debugging` for Task 13 with the approved Edge/Playwright fallback.
- Use the selected reference as the visual target, but render truthful unavailable states wherever the current typed APIs do not expose the pictured data.
- Do not deploy or publish this work.

---

### Task 1: Restore a trustworthy frontend test baseline

**Files:**

- Create: `frontend/src/test/authoritativeFixtures.ts`
- Modify: `frontend/src/components/AssistantPanel.tsx`
- Modify: `frontend/src/components/__tests__/AssistantPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/AssistantPanel.r7.test.tsx`
- Modify: `frontend/src/components/__tests__/AnalysisReviewPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/BaselineParityPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/FeasibilityPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/LlmDiagnosticsPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/MigrationPlanPanel.test.tsx`

**Interfaces:**

- Shared fixtures produce complete `AuthoritativeRunStateDto`, `WorkflowEventDto`, and `ArtifactRefDto` values.
- `AssistantNextSteps` returns before any router-dependent child mounts when the proposal list is empty.
- Existing production prerequisites remain unchanged: analysis waits for parity evidence, feasibility waits for approved G03 plus a physical workspace fingerprint, and planning waits for its authoritative planning events.

- [ ] **Step 1: Record the known RED baseline**

Run from `frontend`:

```powershell
npm test
```

Expected starting evidence: 50 files, 43 passing files, 7 failing files, 201 tests, 180 passing tests, 21 failing tests, and 8 unhandled errors. If counts differ, save the new output and classify every additional failure before editing.

- [ ] **Step 2: Add authoritative fixture builders instead of copying partial states**

Create `src/test/authoritativeFixtures.ts` with these concrete builders:

```ts
import type {
  ArtifactRefDto,
  AuthoritativeRunStateDto,
  WorkflowEventDto,
} from "@/types/generated/api";

export function makeEvent(
  eventType: string,
  sequence: number,
  overrides: Partial<WorkflowEventDto> = {},
): WorkflowEventDto {
  return {
    event_id: `event-${sequence}-${eventType.toLowerCase()}`,
    run_id: "run-fixture",
    stage_id: null,
    event_type: eventType,
    occurred_at: `2026-08-09T10:${String(sequence).padStart(2, "0")}:00Z`,
    sequence,
    payload: {},
    ...overrides,
  };
}

export function makeArtifact(
  overrides: Partial<ArtifactRefDto> = {},
): ArtifactRefDto {
  return {
    artifact_id: "artifact-fixture",
    run_id: "run-fixture",
    stage_id: null,
    artifact_type: "json",
    relative_path: "00_job_setup/fixture.json",
    created_at: "2026-08-09T10:00:00Z",
    checksum: "sha256:fixture",
    ...overrides,
  };
}

export function makeAuthoritativeRun(
  overrides: Partial<AuthoritativeRunStateDto> = {},
): AuthoritativeRunStateDto {
  return {
    run_id: "run-fixture",
    status: "CREATED",
    run_phase: "PREFLIGHT_SNAPSHOT",
    phase_status: "running",
    approval_status: "approved",
    repair_status: "not_required",
    state_version: 1,
    preflight_id: "preflight-fixture",
    source_path: "C:/external/source",
    target_output_path: "C:/external/target/source-angular-21",
    graph_thread_id: "source-intake-run-fixture",
    created_at: "2026-08-09T10:00:00Z",
    updated_at: "2026-08-09T10:00:00Z",
    artifacts: [],
    workflow_events: [makeEvent("RUN_CREATED", 1)],
    ...overrides,
  };
}

export const analysisPrerequisites = [
  makeEvent("G03_APPROVED", 2),
  makeEvent("DISCOVERY_COMPLETED", 3),
  makeEvent("PARITY_BASELINE_COMPLETED", 4),
];

export const feasibilityPrerequisites = [
  ...analysisPrerequisites,
  makeEvent("G04_APPROVED", 5),
];
```

- [ ] **Step 3: Prove the Assistant router defect, then isolate the router-dependent child**

Add an assertion that an assistant message with `next_step_proposals: []` renders without a `next/navigation` mock and produces no unhandled error. Refactor the component to this shape:

```tsx
function AssistantNextStepLink({ runId, proposal }: {
  runId: string;
  proposal: NonNullable<AssistantMessage["next_step_proposals"]>[number];
}) {
  const router = useRouter();
  return (
    <button type="button" onClick={() => router.push(`/migrations/${runId}`)}>
      {proposal.label}
    </button>
  );
}

function AssistantNextSteps({ runId, proposals }: {
  runId: string;
  proposals: NonNullable<AssistantMessage["next_step_proposals"]>;
}) {
  if (proposals.length === 0) return null;
  return <div>{proposals.map((proposal) => (
    <AssistantNextStepLink key={proposal.action_key} runId={runId} proposal={proposal} />
  ))}</div>;
}
```

Retain the existing proposal labels and destination logic inside `AssistantNextStepLink`; only move the hook below the empty-list guard.

- [ ] **Step 4: Replace incomplete panel fixtures with real prerequisites**

Use `analysisPrerequisites` in analysis and baseline-parity tests. Use `feasibilityPrerequisites` in feasibility tests. Add `PARITY_BASELINE_COMPLETED` before expecting analysis review. In feasibility API fixtures that expect a comment form, set `package.workspace_fingerprint` to `sha256:physical-workspace`; retain `null` only in the dedicated legacy regeneration test. Add `G05_APPROVED`, `MIGRATION_PLAN_CREATED`, `STAGE_PLAN_CREATED`, and `G06_CREATED` in that order before expecting planning review controls.

Do not remove the production guards or change blocked guidance into success content.

- [ ] **Step 5: Make LLM diagnostics tests observe settled async state**

Replace immediate assertions after mocked fetches with `findByRole`, `findByText`, or `waitFor`. Reset mocks and fake timers in `afterEach`. Where the component intentionally performs the initial load plus one debounced filter load, assert two calls and inspect the second call's query rather than asserting one total call.

- [ ] **Step 6: Run the focused baseline suite and verify GREEN**

Run from `frontend`:

```powershell
npm test -- src/components/__tests__/AssistantPanel.test.tsx src/components/__tests__/AssistantPanel.r7.test.tsx src/components/__tests__/AnalysisReviewPanel.test.tsx src/components/__tests__/BaselineParityPanel.test.tsx src/components/__tests__/FeasibilityPanel.test.tsx src/components/__tests__/LlmDiagnosticsPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx
npm test
```

Expected: no failed tests and no unhandled errors. If a test still fails, fix the fixture or real defect; do not relax the authoritative prerequisite.

- [ ] **Step 7: Commit the baseline repair**

```powershell
git add frontend/src/test/authoritativeFixtures.ts frontend/src/components/AssistantPanel.tsx frontend/src/components/__tests__/AssistantPanel.test.tsx frontend/src/components/__tests__/AssistantPanel.r7.test.tsx frontend/src/components/__tests__/AnalysisReviewPanel.test.tsx frontend/src/components/__tests__/BaselineParityPanel.test.tsx frontend/src/components/__tests__/FeasibilityPanel.test.tsx frontend/src/components/__tests__/LlmDiagnosticsPanel.test.tsx frontend/src/components/__tests__/MigrationPlanPanel.test.tsx
git commit -m "test(frontend): restore authoritative baseline"
```

---

### Task 2: Build the pure authoritative presentation model

**Files:**

- Create: `frontend/src/presentation/status.ts`
- Create: `frontend/src/presentation/gates.ts`
- Create: `frontend/src/presentation/runJourney.ts`
- Create: `frontend/src/presentation/currentAction.ts`
- Create: `frontend/src/presentation/artifacts.ts`
- Create: `frontend/src/presentation/__tests__/status.test.ts`
- Create: `frontend/src/presentation/__tests__/gates.test.ts`
- Create: `frontend/src/presentation/__tests__/runJourney.test.ts`
- Create: `frontend/src/presentation/__tests__/currentAction.test.ts`
- Create: `frontend/src/presentation/__tests__/artifacts.test.ts`

**Interfaces:**

```ts
export type PresentationTone = "neutral" | "info" | "success" | "warning" | "danger";
export interface StatusPresentation { label: string; tone: PresentationTone; raw: string }

export type JourneyKey =
  | "setup" | "readiness" | "g01" | "baseline" | "discovery" | "feasibility"
  | "plan" | "18-to-19" | "19-to-20" | "20-to-21" | "validate" | "complete";
export type JourneyState =
  | "complete" | "current" | "action-required" | "blocked" | "not-reached" | "unavailable";
export interface JourneyMilestone {
  key: JourneyKey;
  label: string;
  state: JourneyState;
  evidenceEvent?: string;
  stageId?: string;
}

export interface CurrentAction {
  kind: "gate" | "blocked" | "running" | "complete" | "unavailable";
  gateId?: GateId;
  title: string;
  summary: string;
  consequence?: string;
  section: "overview" | "pipeline" | "evidence" | "diagnostics";
  stageKey?: JourneyKey;
  evidenceIds: string[];
  rawSource: string;
}

export interface RunWorkspaceProjection {
  journey: JourneyMilestone[];
  currentAction: CurrentAction;
  completed: string;
  now: string;
  next: string;
}
```

- [ ] **Step 1: Write RED tests for status and gate vocabulary**

Test human labels for representative statuses, unknown raw fallback, and all twelve gate definitions. Include these non-negotiable assertions:

```ts
expect(gateDefinition("G11").label).toBe("Repair validation acceptance");
expect(gateDefinition("G12").label).toBe("Stage-completion acceptance");
expect(presentStatus("TRANSFORMATION_CONTINUATION_BLOCKED")).toEqual({
  label: "Transformation continuation blocked",
  tone: "warning",
  raw: "TRANSFORMATION_CONTINUATION_BLOCKED",
});
expect(presentStatus("FUTURE_BACKEND_VALUE")).toEqual({
  label: "Future backend value",
  tone: "neutral",
  raw: "FUTURE_BACKEND_VALUE",
});
```

Run:

```powershell
npm test -- src/presentation/__tests__/status.test.ts src/presentation/__tests__/gates.test.ts
```

Expected: module-resolution failures because the adapters do not exist.

- [ ] **Step 2: Implement the centralized status and gate registries**

Define `GateId` as `G01` through `G12`. Each `GateDefinition` must contain `label`, `purpose`, `decision`, and terminal decision vocabulary. Use exactly the human-language table in the approved specification. `presentStatus` must first use an explicit map, then convert underscores/hyphens to sentence case while retaining `raw`.

- [ ] **Step 3: Write RED journey tests for absence, order, blockers, and transformation routes**

Cover these cases with `makeAuthoritativeRun` and a minimal typed transformation factory in the test file:

- `RUN_CREATED` without a nonempty preflight binding leaves Setup, Readiness, and G01 unavailable and does not complete Baseline.
- A run with a nonempty `preflight_id` and durable `RUN_CREATED` completes Setup, Readiness, and G01 because authoritative run creation is contractually downstream of approved G01; record `preflight_id` as the evidence source.
- G02-G06 terminal events select the latest created gate outcome by sequence.
- `G05_CREATED` without a terminal event is action required at Feasibility.
- `G06_REJECTED` blocks Plan and leaves transformation milestones not reached.
- route stages `18 -> 19`, `19 -> 20`, and `20 -> 21` map independently.
- missing transformation data is unavailable when transformation evidence exists; it is not complete.
- `STAGED_MIGRATION_COMPLETED` plus `FINAL_TARGET_VERIFIED` completes Validate and Complete.

- [ ] **Step 4: Implement deterministic journey derivation**

Export:

```ts
export function buildJourney(
  run: AuthoritativeRunStateDto,
  transformation: TransformationProjection | null,
  transformationStatus: "disabled" | "loading" | "ready" | "empty" | "failed",
): JourneyMilestone[];
```

Use ordered durable events. Terminal events apply only to their gate instance: scan backward from the latest `Gxx_CREATED` and accept a terminal event occurring after it. Use `TransformationProjection.route_stages` for the three Angular transition milestones. Do not infer a percent and do not compare projection versions.

- [ ] **Step 5: Write RED current-action precedence tests**

Test the exact priority order:

1. valid pending gate;
2. transformation blocked/waiting gate/waiting prompt/active command;
3. run blocked/failure or pending approval;
4. active run work;
5. verified completion;
6. unavailable.

Also assert:

```ts
expect(actionForDifferentProjectionVersions.rawSource).not.toContain("mismatch");
expect(actionDuringRecovery.title).toBe("Authoritative state is refreshing");
expect(actionWithoutGateBindings.kind).not.toBe("gate");
```

- [ ] **Step 6: Implement current action and workspace composition**

Export:

```ts
export function buildRunWorkspaceProjection(
  run: AuthoritativeRunStateDto,
  transformation: TransformationProjection | null,
  transformationStatus: "disabled" | "loading" | "ready" | "empty" | "failed",
  connection: AuthoritativeConnectionStatus,
): RunWorkspaceProjection {
  const journey = buildJourney(run, transformation, transformationStatus);
  const currentAction = selectCurrentAction(run, transformation, transformationStatus, connection);
  return {
    journey,
    currentAction,
    completed: summarizeCompleted(journey),
    now: currentAction.title,
    next: summarizeNext(journey, currentAction),
  };
}
```

When `connection` is `recovering` or `failed`, withhold decision controls in the presentation action. Keep confirmed state visible and route the user to Diagnostics.

- [ ] **Step 7: Implement artifact titles and categories with RED/GREEN tests**

Define `ArtifactCategory` as `gate | command | validation | report | diff | snapshot | diagnostic | other`. Map category from explicit artifact type, stage, and stable path segments. Produce a human title, category, stage label, attempt label, and raw path. Unknown paths must remain selectable under Other.

- [ ] **Step 8: Run presentation tests and commit**

```powershell
npm test -- src/presentation/__tests__
npm run typecheck
git add frontend/src/presentation
git commit -m "feat(frontend): add authoritative presentation model"
```

Expected: presentation tests pass and TypeScript exits `0`.

---

### Task 3: Establish the accessible visual foundation

**Files:**

- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/StatusPill.tsx`
- Create: `frontend/src/components/control-tower/TechnicalDetails.tsx`
- Modify: `frontend/src/components/control-tower/ControlTowerLayout.module.css`
- Modify: `frontend/src/components/ControlTowerShell.module.css`
- Modify: `frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`

**Interfaces:**

- `StatusPill` consumes `StatusPresentation` or a raw value passed through `presentStatus`.
- `TechnicalDetails` is a native disclosure with a stable summary label and wrapping technical values.

- [ ] **Step 1: Add RED component tests for status text and disclosure behavior**

```tsx
render(<StatusPill status="G11_CREATED" />);
expect(screen.getByText("Repair validation acceptance required")).toBeInTheDocument();

render(<TechnicalDetails title="Technical details"><code>sha256:fixture</code></TechnicalDetails>);
expect(screen.getByText("sha256:fixture")).not.toBeVisible();
fireEvent.click(screen.getByText("Technical details"));
expect(screen.getByText("sha256:fixture")).toBeVisible();
```

- [ ] **Step 2: Install the exact icon dependency**

Run from `frontend`:

```powershell
npm install lucide-react@1.31.0 --save-exact
```

Expected: both package files change; no unrelated dependency upgrade.

- [ ] **Step 3: Add the approved tokens and accessibility defaults**

Add to `globals.css`:

```css
:root {
  --color-bg: #07111f;
  --color-surface-1: #0c1a2b;
  --color-surface-2: #10243a;
  --color-border: #29465f;
  --color-text: #f4f7fb;
  --color-text-muted: #aab9c9;
  --color-accent: #58c4e6;
  --color-success: #58d99a;
  --color-warning: #ffb547;
  --color-danger: #f07178;
  --focus-ring: 0 0 0 3px #07111f, 0 0 0 5px #58c4e6;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-12: 3rem;
}

html { background: var(--color-bg); color-scheme: dark; }
body { margin: 0; color: var(--color-text); font: 400 16px/1.5 "Segoe UI", system-ui, sans-serif; }
:focus-visible { outline: 0; box-shadow: var(--focus-ring); }
button, a, input, select, textarea, summary { min-height: 44px; }
code, pre { overflow-wrap: anywhere; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: 0.01ms !important; }
}
```

Retain necessary existing reset rules. Remove duplicated token declarations and mojibake in every touched component.

- [ ] **Step 4: Implement shared status and technical-detail primitives**

Use a visible label plus a Lucide icon; mark a decorative icon `aria-hidden="true"`. `TechnicalDetails` uses `<details>` and `<summary>`, not custom click handlers.

- [ ] **Step 5: Run focused and static checks, then commit**

```powershell
npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
npm run typecheck
npm run lint
git add frontend/package.json frontend/package-lock.json frontend/src/app/globals.css frontend/src/components/StatusPill.tsx frontend/src/components/control-tower/TechnicalDetails.tsx frontend/src/components/control-tower/ControlTowerLayout.module.css frontend/src/components/ControlTowerShell.module.css frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
git commit -m "style(frontend): establish command center foundation"
```

---

### Task 4: Rebuild setup as a four-step preparation flow

**Files:**

- Create: `frontend/src/presentation/setupReadiness.ts`
- Create: `frontend/src/presentation/__tests__/setupReadiness.test.ts`
- Modify: `frontend/src/components/MigrationSetupForm.tsx`
- Modify: `frontend/src/components/MigrationSetupForm.module.css`
- Modify: `frontend/src/components/__tests__/MigrationSetupForm.test.tsx`
- Modify: `frontend/src/app/migrations/new/page.tsx`

**Interfaces:**

```ts
export type SetupStep = "project" | "readiness" | "source-review" | "create-run";
export type ReadinessState = "waiting" | "running" | "passed" | "warning" | "blocked" | "unavailable" | "outdated";
export interface SetupBinding {
  revision: number;
  pathValidationId: string;
  environmentSnapshotId: string;
  sourceAnalysisId: string;
  preflightId: string;
}
```

- [ ] **Step 1: Write RED tests for the new labels, steps, and invalidation**

Update the existing tests to expect **Check readiness**, four labeled steps, real operation states, and **Review production readiness**. Add this core regression:

```tsx
await screen.findByText("Readiness checks passed");
fireEvent.change(screen.getByLabelText("Source path"), {
  target: { value: "C:/external/changed-source" },
});
expect(screen.getByRole("status")).toHaveTextContent("Configuration changed");
expect(screen.getByRole("button", { name: "Check readiness again" })).toBeEnabled();
expect(screen.queryByRole("button", { name: "Review production readiness" })).not.toBeInTheDocument();
```

After recheck, assert the new calls use only the new path-validation/environment/source-analysis IDs.

- [ ] **Step 2: Implement revision-bound readiness state**

On any Step 1 field change, increment `configurationRevision`, retain prior results only as display history marked `outdated`, and clear the active binding and navigable `preflight_id`. Capture the current revision before starting requests and discard a late result when its revision no longer matches.

```ts
const requestRevision = configurationRevision;
const result = await runReadinessChain(values);
if (requestRevision !== configurationRevisionRef.current) return;
setActiveBinding({ revision: requestRevision, ...result.binding });
```

- [ ] **Step 3: Preserve the existing operation chain and make it visible**

Keep the current order: path validation, then environment and source analysis in parallel, then production preflight. Render one status row for each operation. Distinguish warning from blocked; a warning may proceed, while a blocker may not.

- [ ] **Step 4: Implement the four explicit screens**

- Project: source path, external target-parent path, target family, migration mode, and safety explanation.
- Readiness: four operation rows and exact blocker/warning text.
- Source review: detected version/topology/package manager/project count/builder where present, with truthful unavailable labels.
- Create run: approved G01 summary and target boundary. The actual creation remains on the existing G01 route; this step links there with the active preflight ID.

- [ ] **Step 5: Run focused tests and commit**

```powershell
npm test -- src/presentation/__tests__/setupReadiness.test.ts src/components/__tests__/MigrationSetupForm.test.tsx
npm run typecheck
git add frontend/src/presentation/setupReadiness.ts frontend/src/presentation/__tests__/setupReadiness.test.ts frontend/src/components/MigrationSetupForm.tsx frontend/src/components/MigrationSetupForm.module.css frontend/src/components/__tests__/MigrationSetupForm.test.tsx frontend/src/app/migrations/new/page.tsx
git commit -m "feat(frontend): guide migration preparation"
```

---

### Task 5: Create the shared gate-review system and refactor G01

**Files:**

- Create: `frontend/src/components/gates/GateReview.tsx`
- Create: `frontend/src/components/gates/GateDecisionPanel.tsx`
- Create: `frontend/src/components/gates/GateReview.module.css`
- Create: `frontend/src/components/gates/__tests__/GateReview.test.tsx`
- Modify: `frontend/src/components/G01ReviewPanel.tsx`
- Modify: `frontend/src/components/G01ReviewPanel.module.css`
- Modify: `frontend/src/components/__tests__/G01ReviewPanel.test.tsx`
- Modify: `frontend/src/app/preflights/[preflightId]/page.tsx`
- Modify: `frontend/src/app/preflights/[preflightId]/PreflightReviewPage.module.css`

**Interfaces:**

```ts
export interface GateEvidenceGroup {
  title: string;
  summary: string;
  artifactIds: string[];
  status: StatusPresentation;
}

export interface GateReviewModel {
  gateId: GateId;
  status: "pending" | "approved" | "rejected" | "stale" | "expired";
  title: string;
  purpose: string;
  requiredDecision: string;
  verified: string[];
  warnings: string[];
  blockers: string[];
  evidenceGroups: GateEvidenceGroup[];
  technicalBindings: Array<{ label: string; value: string }>;
}
```

- [ ] **Step 1: Write RED shared-gate tests**

Test the specified reading order, technical disclosure, pending decisions, and terminal outcomes. A terminal model must render an outcome card and zero decision buttons.

```tsx
render(<GateReview model={approvedG01} decisionPanel={<button>Approve</button>} />);
expect(screen.getByText("Approved")).toBeInTheDocument();
expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
```

- [ ] **Step 2: Implement `GateReview` as composition, not a domain controller**

It renders purpose, required decision, verified facts, warnings/blockers, evidence groups, reviewer region, and collapsed technical bindings in that order. It accepts backend-permitted controls as children only for a pending model.

- [ ] **Step 3: Refactor G01 into the shared model**

Retain the existing G01 API and decision payload exactly. Move state version, gate version, input checksum, artifact-set checksum, and reservation identifiers into Technical details. Keep source boundary, target reservation, blockers, warnings, and consequence in the primary content.

- [ ] **Step 4: Add terminal and stale-decision tests**

Cover pending, approved, rejected, stale, and expired snapshots. For an API `409`, preserve the reviewer comment in component state, reload the authoritative snapshot, announce that evidence changed, and require a new decision. Assert the failed request never shows a success message.

- [ ] **Step 5: Verify and commit**

```powershell
npm test -- src/components/gates/__tests__/GateReview.test.tsx src/components/__tests__/G01ReviewPanel.test.tsx
npm run typecheck
git add frontend/src/components/gates frontend/src/components/G01ReviewPanel.tsx frontend/src/components/G01ReviewPanel.module.css frontend/src/components/__tests__/G01ReviewPanel.test.tsx frontend/src/app/preflights
git commit -m "feat(frontend): unify governed gate reviews"
```

---

### Task 6: Replace the live-run shell and build the operator Overview

**Files:**

- Modify: `frontend/src/hooks/useTransformation.ts`
- Create: `frontend/src/hooks/__tests__/useTransformation.test.tsx`
- Create: `frontend/src/components/control-tower/RunJourneyStrip.tsx`
- Create: `frontend/src/components/control-tower/CurrentActionCard.tsx`
- Create: `frontend/src/components/control-tower/OperatorOverview.tsx`
- Modify: `frontend/src/components/control-tower/ControlTowerSidebar.tsx`
- Modify: `frontend/src/components/control-tower/ControlTowerHeader.tsx`
- Modify: `frontend/src/components/control-tower/ControlTowerLayout.module.css`
- Modify: `frontend/src/components/AuthoritativeRunDashboard.tsx`
- Modify: `frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx`
- Modify: `frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`

**Interfaces:**

```ts
export type UseTransformationOptions = {
  enabled: boolean;
  refreshKey?: number;
};

export function useTransformation(
  runId: string,
  { enabled, refreshKey = 0 }: UseTransformationOptions,
): {
  projection: TransformationProjection | null;
  executions: CommandExecutionResponseDto[];
  executionStatus: "idle" | "loading" | "ready" | "unavailable";
  status: "disabled" | "loading" | "ready" | "empty" | "failed";
  refresh: () => Promise<void>;
  refreshError: string | null;
  loadError: ApiClientError | null;
};
```

- [ ] **Step 1: Write RED hook tests for single-owner loading**

Assert disabled mode performs zero requests, enabled mode performs one projection request and one execution request, `refreshKey` reloads once, and a background failure retains the last confirmed projection. The disabled `refresh` resolves without a request.

- [ ] **Step 2: Implement enabled transformation loading**

Reset projection only when `runId` changes. In disabled mode set `status: "disabled"` and `executionStatus: "idle"`. The shell enables transformation when `run_phase === "STAGED_MIGRATION"` or any event belongs to `TRANSFORMATION_EVENT_TYPES`.

- [ ] **Step 3: Write RED shell tests for exactly four destinations**

```tsx
expect(screen.getByRole("button", { name: "Overview" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "Pipeline" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "Evidence" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: "Diagnostics" })).toBeInTheDocument();
expect(screen.queryByRole("button", { name: "Transformation" })).not.toBeInTheDocument();
expect(screen.queryByRole("button", { name: "LLM Diagnostics" })).not.toBeInTheDocument();
```

Also test that an action-required projection highlights Pipeline without auto-navigating away from the operator's current section.

- [ ] **Step 4: Implement the four-item shell with Lucide icons**

Set `ControlTowerSection` to `overview | pipeline | evidence | diagnostics`. Use `LayoutDashboard`, `GitBranch`, `FolderSearch`, and `Activity`; put Assistant after the primary nav with a visual separator. Add a skip link before navigation and one route `h1` in the content region.

- [ ] **Step 5: Compose the single presentation projection**

Inside `AuthoritativeRunDashboard`, call `useAuthoritativeRun` once and `useTransformation` once. Pass both to `buildRunWorkspaceProjection`, then pass typed presentation objects downward. Remove local event-name guesses from Overview and remove the `onActionRequiredChange` auto-navigation callback.

- [ ] **Step 6: Build Overview in the selected hierarchy**

Render project header and quiet connection, journey strip, current action above the fold, Completed/Now/Next, evidence at a glance, and collapsed technical details. Current action links set the target section and focused stage; they do not invoke domain commands. Raw event count, artifact count, run ID, and versions stay inside Technical details.

- [ ] **Step 7: Test failure and recovery states**

Add component tests for blocked transformation, running command, verified completion, no available data, reconnecting, event-gap recovery, and incompatible run IDs. When fresh state is required, action controls are disabled and the card says **Authoritative state is refreshing**.

- [ ] **Step 8: Verify and commit**

```powershell
npm test -- src/hooks/__tests__/useTransformation.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx
npm run typecheck
git add frontend/src/hooks/useTransformation.ts frontend/src/hooks/__tests__/useTransformation.test.tsx frontend/src/components/control-tower frontend/src/components/AuthoritativeRunDashboard.tsx frontend/src/components/__tests__/AuthoritativeRunDashboard.test.tsx
git commit -m "feat(frontend): build journey command center shell"
```

---

### Task 7: Rebuild Pipeline as the complete semantic journey through G06

**Files:**

- Modify: `frontend/src/components/control-tower/PipelineSection.tsx`
- Create: `frontend/src/components/control-tower/PipelineStageDetail.tsx`
- Modify: `frontend/src/components/control-tower/ControlTowerLayout.module.css`
- Modify: `frontend/src/components/AuthoritativeRunDashboard.tsx`
- Modify: `frontend/src/components/G02ReviewPanel.tsx`
- Modify: `frontend/src/components/AnalysisReviewPanel.tsx`
- Modify: `frontend/src/components/FeasibilityPanel.tsx`
- Modify: `frontend/src/components/MigrationPlanPanel.tsx`
- Modify: `frontend/src/components/PlanReviewPanel.tsx`
- Modify: `frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`
- Modify: `frontend/src/components/__tests__/G02ReviewPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/AnalysisReviewPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/FeasibilityPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/MigrationPlanPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/PlanReviewPanel.test.tsx`

**Interfaces:**

```ts
export type PipelineTab = "summary" | "command" | "evidence" | "review";
export interface PipelineStageContent {
  milestone: JourneyMilestone;
  group: "prepare" | "baseline" | "understand" | "decide" | "transform" | "validate";
  occurredAt: string | null;
  evidenceCount: number | null;
  tabs: Array<{ id: PipelineTab; label: string; panel: ReactNode }>;
}
```

- [ ] **Step 1: Write RED tests for the full journey and real tabs**

Assert the six group labels, all twelve journey milestones, one expanded row, automatic expansion of current/action-required rows, and manual inspection of completed rows. For tabs, assert `role="tablist"`, selected `role="tab"`, linked `role="tabpanel"`, ArrowLeft/ArrowRight/Home/End keyboard behavior, and absence of tabs whose content is unavailable.

- [ ] **Step 2: Replace local pipeline status inference with `JourneyMilestone` input**

Delete `steps`, `relevant`, and `state` from `PipelineSection.tsx`. The component receives the presentation journey plus structured content. It may control expansion and selected tabs, but it may not inspect raw event names.

- [ ] **Step 3: Place existing G02-G06 surfaces into semantic stages**

- G02 Source snapshot review under Readiness/Prepare.
- G03 baseline acceptance under Baseline.
- Discovery, parity baseline, and G04 under Discovery/Understand.
- Compatibility resolution and G05 under Feasibility/Decide.
- Migration plan and G06 under Plan/Decide.

Keep the existing API hooks and decision payload bindings. Wrap their review content with the shared gate composition where their current data contracts permit it; technical details remain available without leading the page.

- [ ] **Step 4: Make command, evidence, and review tabs truthful**

Only add Command output if an execution/log exists, Evidence if registered artifact IDs exist, and Review if a backend gate package exists. A missing tab is not replaced by synthetic content. Empty Summary uses **Not available from the authoritative state**.

- [ ] **Step 5: Verify early-gate contracts**

Run every existing G02-G06 panel test. Assert expected state version, idempotency key, checksums, and workspace fingerprint remain present in decision calls, and `409` behavior remains fail-closed.

- [ ] **Step 6: Verify and commit**

```powershell
npm test -- src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/G02ReviewPanel.test.tsx src/components/__tests__/AnalysisReviewPanel.test.tsx src/components/__tests__/FeasibilityPanel.test.tsx src/components/__tests__/MigrationPlanPanel.test.tsx src/components/__tests__/PlanReviewPanel.test.tsx
npm run typecheck
git add frontend/src/components/control-tower/PipelineSection.tsx frontend/src/components/control-tower/PipelineStageDetail.tsx frontend/src/components/control-tower/ControlTowerLayout.module.css frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx frontend/src/components/AuthoritativeRunDashboard.tsx frontend/src/components/G02ReviewPanel.tsx frontend/src/components/AnalysisReviewPanel.tsx frontend/src/components/FeasibilityPanel.tsx frontend/src/components/MigrationPlanPanel.tsx frontend/src/components/PlanReviewPanel.tsx frontend/src/components/__tests__/G02ReviewPanel.test.tsx frontend/src/components/__tests__/AnalysisReviewPanel.test.tsx frontend/src/components/__tests__/FeasibilityPanel.test.tsx frontend/src/components/__tests__/MigrationPlanPanel.test.tsx frontend/src/components/__tests__/PlanReviewPanel.test.tsx
git commit -m "feat(frontend): make pipeline journey complete"
```

---

### Task 8: Integrate Transformation and actionable G07-G12 reviews into Pipeline

**Files:**

- Modify: `frontend/src/components/TransformationPanel.tsx`
- Modify: `frontend/src/components/TransformationSections.tsx`
- Modify: `frontend/src/components/TransformationPanel.module.css`
- Modify: `frontend/src/components/AuthoritativeRunDashboard.tsx`
- Modify: `frontend/src/components/control-tower/PipelineStageDetail.tsx`
- Modify: `frontend/src/components/__tests__/TransformationPanel.test.tsx`
- Modify: `frontend/src/presentation/__tests__/gates.test.ts`
- Modify: `frontend/src/presentation/__tests__/currentAction.test.ts`

**Interfaces:**

```ts
export interface TransformationPanelProps {
  runId: string;
  projection: TransformationProjection | null;
  projectionStatus: "disabled" | "loading" | "ready" | "empty" | "failed";
  executions: CommandExecutionResponseDto[];
  executionStatus: "idle" | "loading" | "ready" | "unavailable";
  workflowEvents: WorkflowEventDto[];
  artifacts: ArtifactRefDto[];
  refreshTransformation: () => Promise<void>;
  refreshAuthoritativeState: () => Promise<void>;
}
```

- [ ] **Step 1: Write RED tests proving the panel no longer owns data loading**

Render `TransformationPanel` with props and assert no transformation API mock is called. Test loading, empty, failed, blocked, waiting prompt, active command, and ready projection states.

- [ ] **Step 2: Write explicit actionable G11 and G12 tests**

Use backend-valid projection fixtures with active gate package checksum and workspace fingerprint. Required assertions:

```tsx
expect(screen.getByRole("heading", { name: "Repair validation acceptance" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: /approve repair validation/i })).toBeEnabled();
expect(screen.queryByText("Final stage acceptance")).not.toBeInTheDocument();

expect(screen.getByRole("heading", { name: "Stage-completion acceptance" })).toBeInTheDocument();
expect(screen.getByRole("button", { name: /approve stage completion/i })).toBeEnabled();
expect(screen.queryByText("Delivery approval")).not.toBeInTheDocument();
```

Also assert the submitted calls retain projection state version, package checksum, workspace fingerprint, actor, comment, and idempotency key.

- [ ] **Step 3: Remove `useTransformation` from `TransformationPanel`**

Consume only the shell-owned props. A refresh after decision invokes transformation refresh and authoritative refresh without opening a second interval or event stream.

- [ ] **Step 4: Recompose the transformation stage around the current task**

Order content as: current action, purpose/consequence, evidence required for the action, command/activity if relevant, route stage summary, and collapsed technical details. Remove the nine numbered wall. Keep current decisions expanded; collapse worker internals, fingerprints, raw error payloads, and historical diagnostics.

- [ ] **Step 5: Use the shared gate vocabulary for G07-G12**

Map the active backend gate through `gateDefinition`. G10 exposes only the decisions returned by the existing repair proposal contract. Terminal gates show provenance and no controls. Missing checksum/fingerprint/package means the action is unavailable, not disabled-looking approval.

- [ ] **Step 6: Verify and commit**

```powershell
npm test -- src/components/__tests__/TransformationPanel.test.tsx src/presentation/__tests__/gates.test.ts src/presentation/__tests__/currentAction.test.ts
npm run typecheck
git add frontend/src/components/TransformationPanel.tsx frontend/src/components/TransformationSections.tsx frontend/src/components/TransformationPanel.module.css frontend/src/components/AuthoritativeRunDashboard.tsx frontend/src/components/control-tower/PipelineStageDetail.tsx frontend/src/components/__tests__/TransformationPanel.test.tsx frontend/src/presentation/__tests__/gates.test.ts frontend/src/presentation/__tests__/currentAction.test.ts
git commit -m "feat(frontend): focus transformation gate workflow"
```

---

### Task 9: Build the searchable Evidence master-detail workspace

**Files:**

- Create: `frontend/src/components/control-tower/EvidenceWorkspace.tsx`
- Create: `frontend/src/components/control-tower/EvidenceWorkspace.module.css`
- Create: `frontend/src/components/control-tower/__tests__/EvidenceWorkspace.test.tsx`
- Modify: `frontend/src/components/ArtifactPreviewPanel.tsx`
- Modify: `frontend/src/components/__tests__/ArtifactViewers.test.tsx`
- Modify: `frontend/src/components/AuthoritativeRunDashboard.tsx`
- Modify: `frontend/src/presentation/artifacts.ts`
- Modify: `frontend/src/presentation/__tests__/artifacts.test.ts`

**Interfaces:**

```ts
export interface ArtifactPresentation {
  artifact: ArtifactRefDto;
  title: string;
  category: ArtifactCategory;
  stageLabel: string;
  attemptLabel: string | null;
  searchableText: string;
}
```

- [ ] **Step 1: Write RED master-detail behavior tests**

Test human titles, search by title/path/checksum, category filter, stage filter, empty results, list selection, preview loading failure, and provenance disclosure. At 390 px presentation state, selecting an item switches from list to detail and Back returns to the list.

- [ ] **Step 2: Extend deterministic artifact presentation**

Use the shared mapping for titles/categories. Sort newest first within stable category/stage grouping. Search is case-insensitive and matches human title plus raw metadata. Unknown artifacts remain under Other with their filename as title.

- [ ] **Step 3: Implement desktop split view and mobile list-to-detail**

Desktop renders a filter/search column and preview column. Mobile renders one region at a time without horizontal overflow. Selection is local inspection state only and must not alter backend state.

- [ ] **Step 4: Refactor `ArtifactPreviewPanel` hierarchy**

Lead with human title and preview. Put artifact ID, raw path, type, stage, attempt, producer, timestamp, and checksum under Provenance/Technical details. Preserve `getArtifactById`, existing Markdown/diff/log viewers, and explicit unavailable state.

- [ ] **Step 5: Verify and commit**

```powershell
npm test -- src/presentation/__tests__/artifacts.test.ts src/components/control-tower/__tests__/EvidenceWorkspace.test.tsx src/components/__tests__/ArtifactViewers.test.tsx
npm run typecheck
git add frontend/src/components/control-tower/EvidenceWorkspace.tsx frontend/src/components/control-tower/EvidenceWorkspace.module.css frontend/src/components/control-tower/__tests__/EvidenceWorkspace.test.tsx frontend/src/components/ArtifactPreviewPanel.tsx frontend/src/components/__tests__/ArtifactViewers.test.tsx frontend/src/components/AuthoritativeRunDashboard.tsx frontend/src/presentation/artifacts.ts frontend/src/presentation/__tests__/artifacts.test.ts
git commit -m "feat(frontend): make migration evidence discoverable"
```

---

### Task 10: Consolidate blockers, logs, events, and LLM details into Diagnostics

**Files:**

- Create: `frontend/src/components/control-tower/DiagnosticsWorkspace.tsx`
- Create: `frontend/src/components/control-tower/DiagnosticsWorkspace.module.css`
- Create: `frontend/src/components/control-tower/__tests__/DiagnosticsWorkspace.test.tsx`
- Modify: `frontend/src/components/control-tower/WorkflowEventsSection.tsx`
- Modify: `frontend/src/components/LlmDiagnosticsPanel.tsx`
- Modify: `frontend/src/components/__tests__/LlmDiagnosticsPanel.test.tsx`
- Modify: `frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx`
- Modify: `frontend/src/components/AuthoritativeRunDashboard.tsx`

**Interfaces:**

- Diagnostics subsections: Summary, Blocker, Commands and logs, Workflow events, LLM activity, and Raw state.
- Raw payloads and provider metadata remain available only through explicit disclosure.

- [ ] **Step 1: Write RED diagnostics composition tests**

Test that a blocker summary is first, event names are humanized while raw names remain discoverable, command logs are linked, LLM provider failure is summarized before provider/model/token metadata, empty sections say **Not available**, and connection recovery disables fresh-state actions.

- [ ] **Step 2: Implement the consolidated workspace**

Receive run state, connection state/error, transformation projection/status, executions, and refresh callbacks as props. It may group and filter data but may not open another authoritative subscription.

- [ ] **Step 3: Refactor workflow event presentation**

Keep durable sequence order and search. Display `presentStatus(event.event_type).label`, timestamp, and stage in the row; expose raw event type, sequence, ID, and JSON payload under Technical details.

- [ ] **Step 4: Refactor LLM diagnostics hierarchy**

Keep current API calls and filters. Lead with outcome, affected workflow operation, failure/blocker, and retry availability. Move provider, model, token counts, cost, request IDs, and raw payloads behind Response details. Preserve async settling fixes from Task 1.

- [ ] **Step 5: Verify and commit**

```powershell
npm test -- src/components/control-tower/__tests__/DiagnosticsWorkspace.test.tsx src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx src/components/__tests__/LlmDiagnosticsPanel.test.tsx
npm run typecheck
git add frontend/src/components/control-tower/DiagnosticsWorkspace.tsx frontend/src/components/control-tower/DiagnosticsWorkspace.module.css frontend/src/components/control-tower/__tests__/DiagnosticsWorkspace.test.tsx frontend/src/components/control-tower/WorkflowEventsSection.tsx frontend/src/components/LlmDiagnosticsPanel.tsx frontend/src/components/__tests__/LlmDiagnosticsPanel.test.tsx frontend/src/components/control-tower/__tests__/ControlTowerPresentation.test.tsx frontend/src/components/AuthoritativeRunDashboard.tsx
git commit -m "feat(frontend): consolidate migration diagnostics"
```

---

### Task 11: Make Assistant a subordinate, accessible support drawer

**Files:**

- Modify: `frontend/src/components/AssistantPanel.tsx`
- Modify: `frontend/src/components/AssistantMessage.tsx`
- Modify: `frontend/src/components/AssistantEvidenceDrawer.tsx`
- Create: `frontend/src/components/AssistantPanel.module.css`
- Modify: `frontend/src/components/__tests__/AssistantPanel.test.tsx`
- Modify: `frontend/src/components/__tests__/AssistantPanel.r7.test.tsx`
- Modify: `frontend/src/components/__tests__/AssistantEvidenceDrawer.test.tsx`

**Interfaces:**

- Drawer states: `closed | minimized | expanded`.
- Desktop drawer width: 420-480 px without obscuring current action.
- Mobile: full-height modal sheet with one internal scroll region and focus return.

- [ ] **Step 1: Write RED drawer accessibility tests**

Test open, minimize, restore, Escape close, `aria-modal`, accessible title, initial focus, focus trap, and focus return to the launcher. Test that the launcher does not overlap a primary control at mobile width using class/state assertions plus browser QA in Task 13.

- [ ] **Step 2: Write RED response hierarchy tests**

Assert the visible order: Current state, What is waiting, Why it is blocked, Next permitted action, and Evidence. Internal feature ID, intent/capability key, confidence, model, tokens, and cost must appear only after opening **Response details**.

- [ ] **Step 3: Implement the three-state drawer**

Use `role="dialog"`, `aria-modal="true"` only while expanded, a labeled close button with `X`, and a minimized status bar that does not cover content. Restore focus to the exact invoking control. Respect reduced motion.

- [ ] **Step 4: Recompose assistant messages with shared evidence titles**

Preserve persisted conversation, citations, backend authority, retries, and route proposals. Use `artifactPresentation` for evidence titles and the existing evidence preview. Preserve the router isolation from Task 1.

- [ ] **Step 5: Verify and commit**

```powershell
npm test -- src/components/__tests__/AssistantPanel.test.tsx src/components/__tests__/AssistantPanel.r7.test.tsx src/components/__tests__/AssistantEvidenceDrawer.test.tsx
npm run typecheck
git add frontend/src/components/AssistantPanel.tsx frontend/src/components/AssistantMessage.tsx frontend/src/components/AssistantEvidenceDrawer.tsx frontend/src/components/AssistantPanel.module.css frontend/src/components/__tests__/AssistantPanel.test.tsx frontend/src/components/__tests__/AssistantPanel.r7.test.tsx frontend/src/components/__tests__/AssistantEvidenceDrawer.test.tsx
git commit -m "feat(frontend): subordinate assistant to migration flow"
```

---

### Task 12: Unify landing, routes, mock compatibility, and shell styling

**Files:**

- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/__tests__/page.test.tsx`
- Modify: `frontend/src/app/migrations/[runId]/page.tsx`
- Modify: `frontend/src/app/migrations/new/page.tsx`
- Modify: `frontend/src/components/RunDashboard.tsx`
- Modify: `frontend/src/components/ControlTowerShell.tsx`
- Modify: `frontend/src/components/__tests__/ControlTowerShell.test.tsx`
- Modify: `frontend/src/components/ControlTowerShell.module.css`
- Modify: `frontend/src/components/control-tower/ControlTowerLayout.module.css`
- Modify: `frontend/src/app/globals.css`

**Interfaces:**

- Landing restoration authority and `ACTIVE_RUN_STORAGE_KEY` behavior stay unchanged.
- `mock-*` data passes through a compatibility adapter and uses the same shell primitives; it remains clearly labeled non-authoritative.

- [ ] **Step 1: Write RED landing and compatibility tests**

Test Resume active migration, Start a new migration, plain-language machine readiness, the four-step preparation summary, 404 cleanup, unavailable retry, and preserved active run. Test that mock and authoritative routes expose the same four primary navigation labels and only the mock route shows a non-authoritative notice.

- [ ] **Step 2: Rebuild the landing hierarchy**

Keep restoration logic unchanged. Replace the generic Control Tower introduction with two clear actions and a compact preparation explanation. Put tool paths and raw environment values behind **View diagnostics**.

- [ ] **Step 3: Adapt legacy mock data to shared presentation primitives**

Create the adapter next to `RunDashboard.tsx`; do not coerce mock evidence into authoritative success. Unknown fields map to unavailable. Remove the legacy competing sidebar/header while retaining fixture/demo behavior.

- [ ] **Step 4: Consolidate CSS ownership**

`globals.css` owns reset/tokens/type/focus; `ControlTowerLayout.module.css` owns shell/responsive layout; `ControlTowerShell.module.css` temporarily owns only shared panel/control primitives. Remove duplicated selectors one at a time after their importing component has migrated. Search for and remove mojibake and text-symbol icons from all touched frontend files.

Run:

```powershell
rg -n "Ã|Â|â|ðŸ" src/app src/components
```

Expected: no matches in the redesigned shell and routes.

- [ ] **Step 5: Verify and commit**

```powershell
npm test -- src/app/__tests__/page.test.tsx src/components/__tests__/ControlTowerShell.test.tsx src/components/__tests__/AuthoritativeRunDashboard.test.tsx
npm run typecheck
npm run lint
git add frontend/src/app/page.tsx frontend/src/app/__tests__/page.test.tsx frontend/src/app/migrations/[runId]/page.tsx frontend/src/app/migrations/new/page.tsx frontend/src/app/globals.css frontend/src/components/RunDashboard.tsx frontend/src/components/ControlTowerShell.tsx frontend/src/components/__tests__/ControlTowerShell.test.tsx frontend/src/components/ControlTowerShell.module.css frontend/src/components/control-tower/ControlTowerLayout.module.css
git commit -m "refactor(frontend): unify command center surfaces"
```

---

### Task 13: Complete accessibility, responsive, build, and browser verification

**Files:**

- Create: `frontend/playwright.journey.config.ts`
- Create: `frontend/tests/e2e/journey-command-center.spec.ts`
- Modify: `frontend/package.json`
- Modify: responsive styles touched in Tasks 3-12
- Create after capture: `docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-overview-desktop.png`
- Create after capture: `docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-pipeline-tablet.png`
- Create after capture: `docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-transformation-mobile.png`
- Create after capture: `docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-evidence-desktop.png`

**Interfaces:**

- Viewports: 1440 x 1024, 834 x 1194, and 390 x 844.
- Browser fallback executable: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.
- Real local services: backend `http://127.0.0.1:8000`, frontend `http://127.0.0.1:3000` unless overridden by environment variables.

- [ ] **Step 1: Add the dedicated real-service Playwright configuration**

Do not alter the existing R6 harness configuration. Create `playwright.journey.config.ts` with `baseURL` from `JOURNEY_FRONTEND_URL`, one Edge project using the verified executable, screenshots on failure, trace retention, and no implicit fake backend. Add:

```json
"test:e2e:journey": "playwright test --config playwright.journey.config.ts"
```

- [ ] **Step 2: Add browser journeys**

The spec must cover:

- landing to Prepare migration;
- project input, Check readiness, Configuration changed, and recheck;
- G01 evidence and terminal state when a valid preflight fixture/run is supplied;
- Overview current action to focused Pipeline stage;
- Evidence search/filter/select/preview/provenance;
- Diagnostics blocker/log/event/LLM inspection;
- Assistant open/minimize/close and focus return;
- keyboard navigation across nav, disclosures, real tabs, evidence, and decisions;
- no document horizontal overflow and no fixed element covering current action.

Use `JOURNEY_RUN_ID` for the real authoritative run, `JOURNEY_PREFLIGHT_ID` for G01, and `JOURNEY_SOURCE_PATH` plus `JOURNEY_TARGET_PARENT_PATH` for preparation checks. Fail with a clear setup error when a dependent case lacks its required value; do not silently pass or fabricate state.

- [ ] **Step 3: Run automated frontend gates**

Run from `frontend`:

```powershell
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all commands exit `0`, with no unhandled errors.

- [ ] **Step 4: Start or verify the real local services**

Verify before starting duplicates:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000
```

If unavailable, use the repository's documented backend start command and `npm run dev -- --hostname 127.0.0.1 --port 3000` from `frontend`. Keep long-running processes hidden. Re-run both checks before Playwright.

- [ ] **Step 5: Run desktop, tablet, and mobile browser QA**

```powershell
$env:JOURNEY_FRONTEND_URL='http://127.0.0.1:3000'
$journeyState=Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/runs/run-1e3a2b80415c/state'
$env:JOURNEY_RUN_ID=$journeyState.run_id
$env:JOURNEY_PREFLIGHT_ID=$journeyState.preflight_id
$env:JOURNEY_SOURCE_PATH=$journeyState.source_path
$env:JOURNEY_TARGET_PARENT_PATH=Split-Path -Parent $journeyState.target_output_path
npm run test:e2e:journey
```

Expected: all journeys pass in installed Edge; zero unexpected console errors, failed requests, horizontal overflow, inaccessible controls, or fixed-control obstruction. An intentionally aborted SSE navigation request is acceptable only when the spec explicitly records and filters that exact abort.

- [ ] **Step 6: Capture and compare the built UI to the selected reference**

At identical viewport and state, capture Overview, Pipeline, blocked transformation, and Evidence. Put the selected reference and each built capture into the same visual comparison input, then judge hierarchy, spacing, surface color, line length, current-action emphasis, journey visibility, and progressive disclosure from that combined view. Record visible discrepancies, fix them, and repeat the combined comparison. Do not insert fake data to make the screenshots match.

- [ ] **Step 7: Perform manual accessibility checks**

Verify one `h1` per route, logical heading order, skip link, landmarks, visible focus, keyboard-only operation, restrained live regions, focus movement to blocking errors, dialog focus return, color-plus-text statuses, 44 px targets, readable 16 px body text, and wrapping technical identifiers. Verify mobile Previous/Current/Next journey with expandable full journey.

- [ ] **Step 8: Run repository hygiene and inspect the complete diff**

Run from the repository root:

```powershell
git diff --check
git status --short
git diff --stat
git diff -- frontend
```

Expected: no whitespace errors, no secrets, no generated browser traces/results, and only approved frontend, test, documentation, package, and screenshot changes.

- [ ] **Step 9: Request code review, apply only verified findings, and rerun all gates**

Use `superpowers:requesting-code-review`. Resolve critical/high findings and any authoritative-state, accessibility, or regression issue. Re-run `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`, and `npm run test:e2e:journey` after the final edit.

- [ ] **Step 10: Commit verified completion**

```powershell
git add frontend/playwright.journey.config.ts frontend/tests/e2e/journey-command-center.spec.ts frontend/package.json frontend/package-lock.json frontend/src/app/globals.css frontend/src/components/ControlTowerShell.module.css frontend/src/components/MigrationSetupForm.module.css frontend/src/components/G01ReviewPanel.module.css frontend/src/components/TransformationPanel.module.css frontend/src/components/AssistantPanel.module.css frontend/src/components/control-tower/ControlTowerLayout.module.css frontend/src/components/control-tower/EvidenceWorkspace.module.css frontend/src/components/control-tower/DiagnosticsWorkspace.module.css docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-overview-desktop.png docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-pipeline-tablet.png docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-transformation-mobile.png docs/superpowers/specs/assets/2026-08-09-journey-command-center/built-evidence-desktop.png
git commit -m "feat(frontend): deliver journey command center"
```

Expected: one final verification commit containing only reviewed implementation/test/screenshot changes not already committed by the task-level commits.

---

## Specification Coverage Audit

| Approved requirement | Implemented by |
| --- | --- |
| Exactly four primary destinations | Tasks 6, 10, 12 |
| Global journey from Setup through Complete | Tasks 2, 4, 6, 7, 8 |
| Deterministic current-action precedence | Tasks 2, 6 |
| Projection-local versions never compared | Global constraint, Tasks 2 and 6 |
| Four-step setup and explicit invalidation | Task 4 |
| Shared terminal-safe G01-G12 reviews | Tasks 5, 7, 8 |
| Correct G11/G12 meaning and actionable tests | Tasks 2 and 8 |
| Full semantic Pipeline and real tabs | Task 7 |
| Transformation current task before internals | Task 8 |
| Searchable evidence with preview/provenance | Task 9 |
| Consolidated Diagnostics | Task 10 |
| Subordinate accessible Assistant | Tasks 1 and 11 |
| Central human statuses and real icons | Tasks 2 and 3 |
| Unified landing/mock/authoritative visual system | Task 12 |
| Recovery, stale decisions, missing evidence | Tasks 2, 5, 6, 9, 10 |
| Desktop/tablet/mobile and accessibility | Tasks 3, 4, 6-13 |
| Automated gates and same-state visual comparison | Task 13 |
| No backend behavior or authority changes | Every task; enforced by Global Constraints |
