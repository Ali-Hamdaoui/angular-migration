import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlanningJobStatusCard } from "@/components/PlanningJobStatusCard";
import type { ArtifactRefDto, PlanningJobProjectionDto } from "@/types/generated/api";

const job: PlanningJobProjectionDto = {
  id: "job-1",
  status: "waiting_retry",
  current_step: "generating_plan",
  attempt: 2,
  max_attempts: 3,
  retryable: true,
  next_attempt_at: "2026-07-28T17:00:00Z",
  last_error_code: "PLANNING_EXTERNAL_SERVICE_TRANSIENT",
  last_error_message: "Provider unavailable",
  last_error_stage: "planning_review",
  correlation_id: "planning:run-1",
  updated_at: "2026-07-28T16:59:00Z",
};
const artifact: ArtifactRefDto = {
  artifact_id: "planning-failure-1",
  run_id: "run-1",
  stage_id: null,
  artifact_type: "json",
  relative_path: "03_planning/planning-input-resolution-failure.json",
  created_at: "2026-07-28T16:59:00Z",
  checksum: "sha256:" + "a".repeat(64),
};

describe("PlanningJobStatusCard", () => {
  it("renders automatic retry state, diagnostics, and immutable failure evidence without a manual retry action", () => {
    render(<PlanningJobStatusCard job={job} artifacts={[artifact]} />);
    expect(screen.getByRole("heading", { name: "Planning progress" })).toBeInTheDocument();
    expect(screen.getByText("Automatic retry scheduled")).toBeInTheDocument();
    expect(screen.getByText("Attempt 2 of 3")).toBeInTheDocument();
    expect(screen.getByText("PLANNING_EXTERNAL_SERVICE_TRANSIENT")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open planning failure evidence" })).toHaveAttribute("href", expect.stringContaining("planning-failure-1"));
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });
});
