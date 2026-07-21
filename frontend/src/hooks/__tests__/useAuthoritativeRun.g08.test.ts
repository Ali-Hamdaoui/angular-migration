import { describe, expect, it } from "vitest";
import { AUTHORITATIVE_EVENT_TYPES } from "@/hooks/useAuthoritativeRun";

describe("useAuthoritativeRun G08 event types", () => {
  it("includes APPROVAL_GATE_CREATED", () => {
    expect(AUTHORITATIVE_EVENT_TYPES).toContain("APPROVAL_GATE_CREATED");
  });

  it("includes G08_CREATED", () => {
    expect(AUTHORITATIVE_EVENT_TYPES).toContain("G08_CREATED");
  });

  it("includes G08_APPROVED", () => {
    expect(AUTHORITATIVE_EVENT_TYPES).toContain("G08_APPROVED");
  });

  it("includes G08_MODIFICATION_REQUESTED", () => {
    expect(AUTHORITATIVE_EVENT_TYPES).toContain("G08_MODIFICATION_REQUESTED");
  });

  it("includes G08_REJECTED", () => {
    expect(AUTHORITATIVE_EVENT_TYPES).toContain("G08_REJECTED");
  });

  it("includes G08_STALE", () => {
    expect(AUTHORITATIVE_EVENT_TYPES).toContain("G08_STALE");
  });

  it("does not include unexpected G08 event types", () => {
    const g08Events = AUTHORITATIVE_EVENT_TYPES.filter((t) => t.startsWith("G08"));
    expect(g08Events).toEqual([
      "G08_CREATED",
      "G08_APPROVED",
      "G08_MODIFICATION_REQUESTED",
      "G08_REJECTED",
      "G08_STALE",
    ]);
  });
});
