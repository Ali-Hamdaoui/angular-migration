import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FailureEvidenceViewer } from "@/components/FailureEvidenceViewer";
import type { FailureEvidenceDto } from "@/types/generated/api";

const sampleEvidence: FailureEvidenceDto = {
  failure_id: "failure-001",
  run_id: "run-001",
  stage_id: "stage-1",
  execution_id: "exec-001",
  failure_fingerprint: "sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
  origin: "migration_caused",
  diagnostics: [
    {
      parser_type: "typescript",
      parser_confidence: 0.9,
      message: "TS2322: Type 'string' is not assignable to type 'number'",
      code: "TS2322",
      file_path: "src/app/component.ts",
      line_number: 15,
      column: 5,
      severity: "error",
    },
    {
      parser_type: "npm",
      parser_confidence: 0.85,
      message: "npm ERR! code ELIFECYCLE",
      severity: "error",
    },
  ],
  workspace_fingerprint: "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  status: "finalized",
  raw_log_artifacts: [],
  state_version: 1,
};

describe("FailureEvidenceViewer", () => {
  it("renders loading state", () => {
    render(<FailureEvidenceViewer evidence={null} loading={true} />);
    expect(screen.getByText(/loading failure evidence/i)).toBeTruthy();
  });

  it("renders error state", () => {
    render(<FailureEvidenceViewer evidence={null} loading={false} error="Connection failed" />);
    expect(screen.getByText(/Error:/)).toBeTruthy();
    expect(screen.getByText(/Connection failed/)).toBeTruthy();
  });

  it("renders empty state when no evidence", () => {
    render(<FailureEvidenceViewer evidence={null} loading={false} />);
    expect(screen.getByText(/No failure evidence/)).toBeTruthy();
  });

  it("renders evidence with diagnostics", () => {
    render(<FailureEvidenceViewer evidence={sampleEvidence} loading={false} />);
    expect(screen.getByText("Failure Evidence")).toBeTruthy();
    expect(screen.getByText(/TS2322/)).toBeTruthy();
    expect(screen.getByText(/npm ERR/)).toBeTruthy();
  });

  it("shows origin badge", () => {
    render(<FailureEvidenceViewer evidence={sampleEvidence} loading={false} />);
    expect(screen.getByText(/migration caused/)).toBeTruthy();
  });

  it("shows fingerprint", () => {
    render(<FailureEvidenceViewer evidence={sampleEvidence} loading={false} />);
    expect(screen.getByText(/FP:/)).toBeTruthy();
  });

  it("switches between raw and normalized tabs", () => {
    render(<FailureEvidenceViewer evidence={sampleEvidence} loading={false} />);
    const normalizedTab = screen.getByText("Normalized Diagnostics");
    const rawTab = screen.getByText("Raw Output");
    expect(normalizedTab).toBeTruthy();
    expect(rawTab).toBeTruthy();

    fireEvent.click(rawTab);
    expect(screen.getByText(/raw stdout\/stderr/)).toBeTruthy();

    fireEvent.click(normalizedTab);
    expect(screen.getByText("TS2322")).toBeTruthy();
  });

  it("filters diagnostics by text", () => {
    render(<FailureEvidenceViewer evidence={sampleEvidence} loading={false} />);
    const input = screen.getByLabelText("Filter diagnostics");
    fireEvent.change(input, { target: { value: "TS2322" } });
    expect(screen.getByText(/1 of 2 diagnostics/)).toBeTruthy();
  });

  it("filters diagnostics by parser type", () => {
    render(<FailureEvidenceViewer evidence={sampleEvidence} loading={false} />);
    const select = screen.getByLabelText("Filter by parser type");
    fireEvent.change(select, { target: { value: "npm" } });
    expect(screen.getByText(/npm ERR/)).toBeTruthy();
  });

  it("shows unknown origin badge", () => {
    const unknownEvidence: FailureEvidenceDto = {
      ...sampleEvidence,
      origin: "unknown_origin",
    };
    render(<FailureEvidenceViewer evidence={unknownEvidence} loading={false} />);
    expect(screen.getByText(/unknown origin/)).toBeTruthy();
  });
});
