import { gateDefinition, isGateId, type GateId } from "@/presentation/gates";

const expectedGates: Array<[GateId, string, string]> = [
  ["G01", "Production readiness", "Confirm the environment, source boundary, and reserved target are safe enough to create a run."],
  ["G02", "Source snapshot", "Confirm the immutable source snapshot represents the intended application."],
  ["G03", "Baseline acceptance", "Confirm the known pre-migration state and its proven or attested failures."],
  ["G04", "Analysis review", "Confirm the analysis findings, risks, unknowns, and support classification."],
  ["G05", "Migration readiness approval", "Decide whether the requested migration route may proceed."],
  ["G06", "Migration plan approval", "Lock the execution contract, route, commands, validation, recovery, and delivery strategy."],
  ["G07", "Stage-start acceptance", "Confirm the current stage input, workspace fingerprint, and exact stage plan."],
  ["G08", "Transformation acceptance", "Review the official Angular migration output, diffs, migration ledger, and preliminary target version."],
  ["G09", "Validation acceptance", "Review the complete stage validation and parity evidence."],
  ["G10", "Repair proposal", "Apply, reject, or request revision of one exact reviewed repair patch."],
  ["G11", "Repair validation acceptance", "Confirm the applied repair through the normal validation pipeline and error delta."],
  ["G12", "Stage-completion acceptance", "Approve cleanliness, output fingerprint, evidence index, sealing, and copy-forward readiness."],
];

describe("gateDefinition", () => {
  it.each(expectedGates)("defines the approved vocabulary for %s", (gateId, label, decision) => {
    const definition = gateDefinition(gateId);

    expect(definition).toMatchObject({ id: gateId, label, decision });
    expect(definition.purpose).not.toBe("");
    expect(definition.terminalDecisionLabels).toEqual({
      approved: "Approved",
      approved_with_risk: "Approved with risk",
      modification_requested: "Modification requested",
      rejected: "Rejected",
      stale: "Stale",
      expired: "Expired",
      cancelled: "Cancelled",
    });
  });

  it("keeps the repair validation label assigned to G11", () => {
    expect(gateDefinition("G11").label).toBe("Repair validation acceptance");
  });

  it("keeps the stage-completion label assigned to G12", () => {
    expect(gateDefinition("G12").label).toBe("Stage-completion acceptance");
  });

  it("rejects prototype-like unknown backend gate identifiers", () => {
    expect(isGateId("toString")).toBe(false);
  });
});
