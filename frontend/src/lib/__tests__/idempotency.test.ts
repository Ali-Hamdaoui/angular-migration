import { describe, expect, it, vi } from "vitest";
import { createLogicalOperationKeys } from "@/lib/idempotency";

describe("createLogicalOperationKeys", () => {
  it("reuses one key for transport retries and rotates only after the logical operation completes", () => {
    const uuid = vi.fn().mockReturnValueOnce("one").mockReturnValueOnce("two");
    const keys = createLogicalOperationKeys("analysis-run-1", uuid);
    expect(keys.get("retry-analysis-1")).toBe("analysis-run-1-retry-analysis-1-one");
    expect(keys.get("retry-analysis-1")).toBe("analysis-run-1-retry-analysis-1-one");
    expect(uuid).toHaveBeenCalledTimes(1);
    keys.complete("retry-analysis-1");
    expect(keys.get("retry-analysis-1")).toBe("analysis-run-1-retry-analysis-1-two");
  });
});
