import { fireEvent, render, screen } from "@testing-library/react";
import { FailureEvidenceViewer } from "@/components/FailureEvidenceViewer";
import type { FailureEvidenceDto, FailureDiagnosticDto } from "@/types/generated/api";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function makeDiagnostic(overrides: Partial<FailureDiagnosticDto> = {}): FailureDiagnosticDto {
  return {
    parser_type: "typescript",
    parser_confidence: 0.92,
    message: "Type 'string' is not assignable to type 'number'.",
    code: "TS2322",
    file_path: "src/app/app.component.ts",
    line_number: 42,
    column: 10,
    severity: "error",
    raw_excerpt: "src/app/app.component.ts:42:10 - error TS2322: Type 'string' is not assignable to type 'number'.",
    source_line: "  const x: number = 'hello';",
    ...overrides,
  };
}

function makeEvidence(overrides: Partial<FailureEvidenceDto> = {}): FailureEvidenceDto {
  return {
    failure_id: "fail-001",
    run_id: "run-abc",
    stage_id: "stage-01",
    execution_id: "exec-001",
    failure_fingerprint: "sha256:a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b",
    origin: "migration_caused",
    diagnostics: [
      makeDiagnostic(),
      makeDiagnostic({
        parser_type: "npm",
        parser_confidence: 0.75,
        message: "Package 'foo' not found in registry.",
        code: "ERR_MODULE_NOT_FOUND",
        file_path: "package.json",
        severity: "warning",
      }),
      makeDiagnostic({
        parser_type: "angular_cli",
        parser_confidence: 0.88,
        message: "Angular CLI version mismatch.",
        code: "NG_VERSION_MISMATCH",
        file_path: "angular.json",
        severity: "error",
      }),
    ],
    workspace_fingerprint: "sha256:workspace-fingerprint-value",
    status: "finalized",
    raw_log_artifacts: [{ artifact_id: "art-001", checksum: "sha256:log", content_type: "text/plain" }],
    state_version: 5,
    created_at: "2025-06-15T10:30:00Z",
    ...overrides,
  };
}

/* ================================================================== */
/*  Tests                                                              */
/* ================================================================== */

describe("FailureEvidenceViewer", () => {
  /* ------------------------------------------------------------------ */
  /*  Renders with full evidence data                                    */
  /* ------------------------------------------------------------------ */
  it("renders with full evidence data", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // Check title
    expect(screen.getByRole("heading", { name: "Failure Evidence" })).toBeInTheDocument();

    // Check origin badge
    expect(screen.getByText("Migration Caused")).toBeInTheDocument();

    // Check fingerprint (truncated)
    expect(screen.getByText(/sha256:a1b2c3d4e5f6a7b8…/)).toBeInTheDocument();

    // Check status pill
    expect(screen.getByText("finalized")).toBeInTheDocument();

    // Check metadata
    expect(screen.getByText("fail-001")).toBeInTheDocument();
    expect(screen.getByText("run-abc")).toBeInTheDocument();
    expect(screen.getByText("stage-01")).toBeInTheDocument();
    expect(screen.getByText("exec-001")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();

    // Check the diagnostics tab is active by default
    expect(screen.getByText("TS2322")).toBeInTheDocument();
    expect(screen.getByText("Type 'string' is not assignable to type 'number'.")).toBeInTheDocument();
    expect(screen.getByText("ERR_MODULE_NOT_FOUND")).toBeInTheDocument();
    expect(screen.getByText("NG_VERSION_MISMATCH")).toBeInTheDocument();

    // Check parser badges
    expect(screen.getByText("TYPESCRIPT")).toBeInTheDocument();
    expect(screen.getByText("NPM")).toBeInTheDocument();
    expect(screen.getByText("ANGULAR CLI")).toBeInTheDocument();

    // Check file paths
    expect(screen.getByText(/src\/app\/app\.component\.ts/)).toBeInTheDocument();
    expect(screen.getByText(/package\.json/)).toBeInTheDocument();
    expect(screen.getByText(/angular\.json/)).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Shows loading state                                                */
  /* ------------------------------------------------------------------ */
  it("shows loading state", () => {
    render(
      <FailureEvidenceViewer evidence={null} loading={true} error={null} />,
    );

    expect(screen.getByText("Loading failure evidence…")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Shows error state                                                  */
  /* ------------------------------------------------------------------ */
  it("shows error state", () => {
    render(
      <FailureEvidenceViewer
        evidence={null}
        loading={false}
        error="Failed to fetch failure evidence: 500 Internal Server Error"
      />,
    );

    expect(
      screen.getByText(
        "Failed to fetch failure evidence: 500 Internal Server Error",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Shows empty / no-evidence state                                    */
  /* ------------------------------------------------------------------ */
  it("shows empty/no-evidence state", () => {
    render(
      <FailureEvidenceViewer evidence={null} loading={false} error={null} />,
    );

    expect(
      screen.getByText("No failure evidence available for this execution."),
    ).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Raw / normalized tabs work                                         */
  /* ------------------------------------------------------------------ */
  it("switches between raw and normalized tabs", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // Parsed Diagnostics tab is active by default
    const parsedTab = screen.getByRole("tab", { name: "Parsed Diagnostics" });
    const rawTab = screen.getByRole("tab", { name: "Raw Output" });

    expect(parsedTab).toHaveAttribute("aria-selected", "true");
    expect(rawTab).toHaveAttribute("aria-selected", "false");

    // Switch to raw
    fireEvent.click(rawTab);
    expect(rawTab).toHaveAttribute("aria-selected", "true");
    expect(parsedTab).toHaveAttribute("aria-selected", "false");

    // Switch back to parsed
    fireEvent.click(parsedTab);
    expect(parsedTab).toHaveAttribute("aria-selected", "true");
    expect(rawTab).toHaveAttribute("aria-selected", "false");
  });

  /* ------------------------------------------------------------------ */
  /*  Raw tab shows command output                                       */
  /* ------------------------------------------------------------------ */
  it("shows raw output in raw tab", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    const rawTab = screen.getByRole("tab", { name: "Raw Output" });
    fireEvent.click(rawTab);

    // Should include raw excerpts from diagnostics
    expect(
      screen.getByText(
        /src\/app\/app\.component\.ts:42:10 - error TS2322/,
      ),
    ).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  File / parser filtering works                                      */
  /* ------------------------------------------------------------------ */
  it("filters diagnostics by file path", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // All three diagnostics should be visible initially
    expect(screen.getByText("TYPESCRIPT")).toBeInTheDocument();
    expect(screen.getByText("NPM")).toBeInTheDocument();
    expect(screen.getByText("ANGULAR CLI")).toBeInTheDocument();

    // Type in filter to show only package.json-related entries
    const filterInput = screen.getByRole("searchbox", { name: "Filter diagnostics" });
    fireEvent.change(filterInput, { target: { value: "package.json" } });

    // NPM diagnostic should remain, others filtered out
    expect(screen.getByText("NPM")).toBeInTheDocument();
    expect(screen.queryByText("TYPESCRIPT")).not.toBeInTheDocument();
    expect(screen.queryByText("ANGULAR CLI")).not.toBeInTheDocument();
  });

  it("filters diagnostics by parser type via select", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    const parserSelect = screen.getByRole("combobox", {
      name: "Filter by parser type",
    });

    // Select "TYPESCRIPT" parser
    fireEvent.change(parserSelect, { target: { value: "typescript" } });

    expect(screen.getByText("TYPESCRIPT")).toBeInTheDocument();
    expect(screen.queryByText("NPM")).not.toBeInTheDocument();
    expect(screen.queryByText("ANGULAR CLI")).not.toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Parser confidence indicator                                         */
  /* ------------------------------------------------------------------ */
  it("displays parser confidence indicators", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // Check confidence percentages are shown
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("88%")).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Baseline origin badge                                               */
  /* ------------------------------------------------------------------ */
  it("displays correct origin badge for each origin type", () => {
    const origins: Array<[FailureEvidenceDto["origin"], string]> = [
      ["pre_existing_unchanged", "Pre-Existing Unchanged"],
      ["pre_existing_changed", "Pre-Existing Changed"],
      ["migration_caused", "Migration Caused"],
      ["resolved_pre_existing", "Resolved Pre-Existing"],
      ["unknown_origin", "Unknown Origin"],
    ];

    for (const [origin, label] of origins) {
      const { unmount } = render(
        <FailureEvidenceViewer
          evidence={makeEvidence({ origin })}
          loading={false}
          error={null}
        />,
      );
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  /* ------------------------------------------------------------------ */
  /*  Fingerprint display                                                */
  /* ------------------------------------------------------------------ */
  it("displays truncated sha256 fingerprint", () => {
    const evidence = makeEvidence({
      failure_fingerprint:
        "sha256:a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b",
    });
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // Should show truncated version with "sha256:" prefix and first 16 hex chars + ellipsis
    expect(screen.getByText(/sha256:a1b2c3d4e5f6a7b8…/)).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Unknown state display                                              */
  /* ------------------------------------------------------------------ */
  it("shows unknown state when origin is unknown", () => {
    const evidence = makeEvidence({ origin: "unknown_origin" });
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    expect(
      screen.getByText(
        "Origin not determined — the failure source could not be classified.",
      ),
    ).toBeInTheDocument();
  });

  it("shows unknown state when fingerprint is empty", () => {
    const evidence = makeEvidence({ failure_fingerprint: "" });
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    expect(screen.getByText("No fingerprint recorded.")).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Stale state display                                                */
  /* ------------------------------------------------------------------ */
  it("shows stale state banner", () => {
    const evidence = makeEvidence({ status: "stale" });
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    expect(
      screen.getByText(
        /This evidence record is stale/,
      ),
    ).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Does not advance workflow locally                                  */
  /* ------------------------------------------------------------------ */
  it("does not advance workflow locally (no API calls, no state mutation buttons)", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // There should be no buttons that advance workflow — only tab switches and filter inputs
    const buttons = screen.getAllByRole("button");
    for (const btn of buttons) {
      // Tab buttons are safe — they only switch view mode
      expect(btn.getAttribute("role")).toBe("tab");
    }

    // No form submission or workflow-affecting controls
    expect(
      screen.queryByRole("button", { name: /approve|reject|start|run|advance|submit|confirm/i }),
    ).not.toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Accessible labels and keyboard operation                           */
  /* ------------------------------------------------------------------ */
  it("has accessible labels on all interactive elements", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // Tab list has label
    expect(
      screen.getByRole("tablist", { name: "Evidence view mode" }),
    ).toBeInTheDocument();

    // Each tab is a button with role="tab"
    expect(
      screen.getByRole("tab", { name: "Raw Output" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Parsed Diagnostics" }),
    ).toBeInTheDocument();

    // Filter input has label
    expect(
      screen.getByRole("searchbox", { name: "Filter diagnostics" }),
    ).toBeInTheDocument();

    // Parser select has label
    expect(
      screen.getByRole("combobox", { name: "Filter by parser type" }),
    ).toBeInTheDocument();
  });

  it("supports keyboard navigation on tab list (ArrowLeft / ArrowRight)", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    const rawTab = screen.getByRole("tab", { name: "Raw Output" });
    const parsedTab = screen.getByRole("tab", { name: "Parsed Diagnostics" });

    // Start with Parsed Diagnostics selected
    expect(parsedTab).toHaveAttribute("aria-selected", "true");

    // Press ArrowLeft on the tab list — should select Raw Output
    const tabList = screen.getByRole("tablist");
    fireEvent.keyDown(tabList, { key: "ArrowLeft" });
    expect(rawTab).toHaveAttribute("aria-selected", "true");
    expect(parsedTab).toHaveAttribute("aria-selected", "false");

    // Press ArrowRight — should select Parsed Diagnostics again
    fireEvent.keyDown(tabList, { key: "ArrowRight" });
    expect(parsedTab).toHaveAttribute("aria-selected", "true");
    expect(rawTab).toHaveAttribute("aria-selected", "false");
  });

  /* ------------------------------------------------------------------ */
  /*  Empty diagnostics with filters                                     */
  /* ------------------------------------------------------------------ */
  it("shows empty state when filter matches no diagnostics", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    const filterInput = screen.getByRole("searchbox", { name: "Filter diagnostics" });
    fireEvent.change(filterInput, { target: { value: "NONEXISTENT_FILE_XYZ" } });

    expect(
      screen.getByText("No diagnostics match the current filters."),
    ).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Filter count display                                               */
  /* ------------------------------------------------------------------ */
  it("shows filter count of diagnostics", () => {
    const evidence = makeEvidence();
    render(<FailureEvidenceViewer evidence={evidence} loading={false} error={null} />);

    // Should show "3 of 3 diagnostics"
    expect(screen.getByText(/3 of 3/)).toBeInTheDocument();
  });
});
