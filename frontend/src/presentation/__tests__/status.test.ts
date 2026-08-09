import { presentStatus } from "@/presentation/status";

describe("presentStatus", () => {
  it.each([
    ["COMPLETED", "Complete", "success"],
    ["RUNNING", "Running", "info"],
    ["WAITING_APPROVAL", "Waiting for approval", "warning"],
    ["FAILED", "Failed", "danger"],
  ] as const)("presents %s with explicit human vocabulary", (raw, label, tone) => {
    expect(presentStatus(raw)).toEqual({ label, tone, raw });
  });

  it("presents a transformation continuation blocker as a warning", () => {
    expect(presentStatus("TRANSFORMATION_CONTINUATION_BLOCKED")).toEqual({
      label: "Transformation continuation blocked",
      tone: "warning",
      raw: "TRANSFORMATION_CONTINUATION_BLOCKED",
    });
  });

  it("keeps an exact lowercase backend blocker in the warning registry", () => {
    expect(presentStatus("blocked")).toEqual({
      label: "Blocked",
      tone: "warning",
      raw: "blocked",
    });
  });

  it("preserves unknown backend values while deriving a neutral label", () => {
    expect(presentStatus("FUTURE_BACKEND_VALUE")).toEqual({
      label: "Future backend value",
      tone: "neutral",
      raw: "FUTURE_BACKEND_VALUE",
    });
  });
});
