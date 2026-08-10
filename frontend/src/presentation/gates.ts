export type GateId =
  | "G01"
  | "G02"
  | "G03"
  | "G04"
  | "G05"
  | "G06"
  | "G07"
  | "G08"
  | "G09"
  | "G10"
  | "G11"
  | "G12";

export interface GateDefinition {
  id: GateId;
  label: string;
  purpose: string;
  decision: string;
  terminalDecisionLabels: {
    approved: string;
    approved_with_risk: string;
    modification_requested: string;
    rejected: string;
    stale: string;
    expired: string;
    cancelled: string;
  };
}

const TERMINAL_DECISION_LABELS = {
  approved: "Approved",
  approved_with_risk: "Approved with risk",
  modification_requested: "Modification requested",
  rejected: "Rejected",
  stale: "Stale",
  expired: "Expired",
  cancelled: "Cancelled",
} as const;

const gate = (id: GateId, label: string, decision: string): GateDefinition => ({
  id,
  label,
  purpose: `Review ${label.toLowerCase()} evidence before the journey continues.`,
  decision,
  terminalDecisionLabels: TERMINAL_DECISION_LABELS,
});

const GATE_DEFINITIONS: Record<GateId, GateDefinition> = {
  G01: gate("G01", "Production readiness", "Confirm the environment, source boundary, and reserved target are safe enough to create a run."),
  G02: gate("G02", "Source snapshot", "Confirm the immutable source snapshot represents the intended application."),
  G03: gate("G03", "Baseline acceptance", "Confirm the known pre-migration state and its proven or attested failures."),
  G04: gate("G04", "Analysis review", "Confirm the analysis findings, risks, unknowns, and support classification."),
  G05: gate("G05", "Migration readiness approval", "Decide whether the requested migration route may proceed."),
  G06: gate("G06", "Migration plan approval", "Lock the execution contract, route, commands, validation, recovery, and delivery strategy."),
  G07: gate("G07", "Stage-start acceptance", "Confirm the current stage input, workspace fingerprint, and exact stage plan."),
  G08: gate("G08", "Transformation acceptance", "Review the official Angular migration output, diffs, migration ledger, and preliminary target version."),
  G09: gate("G09", "Validation acceptance", "Review the complete stage validation and parity evidence."),
  G10: gate("G10", "Repair proposal", "Apply, reject, or request revision of one exact reviewed repair patch."),
  G11: gate("G11", "Repair validation acceptance", "Confirm the applied repair through the normal validation pipeline and error delta."),
  G12: gate("G12", "Stage-completion acceptance", "Approve cleanliness, output fingerprint, evidence index, sealing, and copy-forward readiness."),
};

export function gateDefinition(gateId: GateId): GateDefinition {
  return GATE_DEFINITIONS[gateId];
}

export function isGateId(value: string | null | undefined): value is GateId {
  return value != null && Object.prototype.hasOwnProperty.call(GATE_DEFINITIONS, value);
}
