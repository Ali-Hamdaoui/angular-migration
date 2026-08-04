import { describe, expect, it } from "vitest";
import { formatEventLabel, formatPhaseLabel, formatStatusLabel } from "../presentationLabels";

describe("presentation labels", () => {
  it("maps known status values to readable labels", () => {
    expect(formatStatusLabel("SOURCE_VALIDATED")).toBe("Source validated");
    expect(formatStatusLabel("WAITING")).toBe("Waiting for approval");
    expect(formatStatusLabel("RUNNING")).toBe("In progress");
    expect(formatStatusLabel("COMPLETED")).toBe("Completed");
    expect(formatStatusLabel("FAILED")).toBe("Failed");
    expect(formatStatusLabel("BLOCKED")).toBe("Blocked");
    expect(formatStatusLabel("pending")).toBe("Pending approval");
    expect(formatStatusLabel("approved")).toBe("Approved");
    expect(formatStatusLabel("rejected")).toBe("Rejected");
    expect(formatStatusLabel("stale")).toBe("Needs refresh");
  });

  it("maps known phase values to readable labels", () => {
    expect(formatPhaseLabel("PREFLIGHT_SNAPSHOT")).toBe("Source snapshot");
    expect(formatPhaseLabel("G02_REVIEW")).toBe("Source approval");
    expect(formatPhaseLabel("BASELINE_VALIDATION")).toBe("Baseline checks");
    expect(formatPhaseLabel("TRANSFORMATION")).toBe("Migration execution");
  });

  it("maps known event values to readable labels", () => {
    expect(formatEventLabel("G02_APPROVED")).toBe("Source approved");
    expect(formatEventLabel("BASELINE_INSTALL_SUCCEEDED")).toBe("Dependencies installed");
    expect(formatEventLabel("G06_APPROVED")).toBe("Plan approved");
    expect(formatEventLabel("COMMAND_STARTED")).toBe("Command started");
  });

  it("uses a safe sentence-case fallback for unknown values", () => {
    expect(formatStatusLabel("SOME_UNKNOWN_STATUS")).toBe("Some unknown status");
    expect(formatPhaseLabel("MYSTERY_PHASE")).toBe("Mystery phase");
    expect(formatEventLabel("MYSTERY_EVENT")).toBe("Mystery event");
  });

  it("never mutates the original value", () => {
    const raw = "G02_APPROVED";
    const formatted = formatEventLabel(raw);
    expect(formatted).toBe("Source approved");
    expect(raw).toBe("G02_APPROVED");
  });
});