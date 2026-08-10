import {
  buildSourceReviewSummary,
  environmentReadinessState,
  pathReadinessState,
  preflightReadinessState,
  sourceReadinessState,
} from "@/presentation/setupReadiness";
import type { SourceAnalysisResult } from "@/api/migrations";
import type { PathValidationResult } from "@/types/generated/api";

const unavailable = "Not available from readiness evidence";

const sourceAnalysis = {
  snapshot: {
    analysis_id: "analysis-1",
    policy_version: "source-analysis-v1",
    status: "review_required",
    source_path: "C:/external/source",
    package_manager: "npm",
    lockfile: "package-lock.json",
    versions: [
      { package: "@angular/core", declared: "^20.2.0", resolved: "20.2.4", family: "20.x", confidence: "high" },
      { package: "rxjs", declared: "^7.8.0", resolved: null, family: "7.x", confidence: "medium" },
    ],
    topology: {
      projects: ["portal", "admin"],
      libraries: ["ui"],
      is_nx: true,
      has_custom_builder: true,
      classification: "nx-monorepo",
    },
    blockers: [],
    warnings: ["CUSTOM_BUILDER_REVIEW_REQUIRED"],
    checksum: "sha256:source",
  },
} as SourceAnalysisResult;

const pathValidation = {
  snapshot: {
    validation_id: "path-1",
    captured_at: "2026-08-09T10:00:00Z",
    policy_version: "path-validation-v2-external-output",
    status: "passed",
    source_path: "C:/external/source",
    target_parent_path: "C:/external/target",
    generated_output_name: "source-angular-21",
    resolved_output_root: "C:/external/target/source-angular-21",
    reservation_id: "reservation-1",
    reservation_expires_at: "2026-08-09T11:00:00Z",
    target_output_path: "C:/external/target/source-angular-21",
    source_fingerprint: "sha256:source",
    rules: [],
    blockers: [],
    warnings: [],
    target_reservation_eligible: true,
    checksum: "sha256:path",
  },
} satisfies PathValidationResult;

describe("setup readiness status adapters", () => {
  it.each([
    ["passed", "passed"],
    ["passed_with_warnings", "warning"],
    ["blocked", "blocked"],
    ["passed-later", "unavailable"],
    ["prefix-passed", "unavailable"],
    ["unknown", "unavailable"],
  ])("maps exact path status %s to %s", (status, expected) => {
    expect(pathReadinessState(status)).toBe(expected);
  });

  it.each([
    ["available", "passed"],
    ["degraded", "warning"],
    ["blocked", "blocked"],
    ["available_after_refresh", "unavailable"],
    ["unknown", "unavailable"],
  ])("maps exact environment status %s to %s", (status, expected) => {
    expect(environmentReadinessState(status)).toBe(expected);
  });

  it.each([
    ["accepted", "passed"],
    ["review_required", "warning"],
    ["blocked", "blocked"],
    ["accepted_with_notes", "unavailable"],
    ["unknown", "unavailable"],
  ])("maps exact source status %s to %s", (status, expected) => {
    expect(sourceReadinessState(status)).toBe(expected);
  });

  it.each([
    ["passed", "passed"],
    ["passed_with_warnings", "warning"],
    ["blocked", "blocked"],
    ["expired", "outdated"],
    ["stale", "outdated"],
    ["passed_after_retry", "unavailable"],
    ["unknown", "unavailable"],
  ])("maps exact preflight status %s to %s", (status, expected) => {
    expect(preflightReadinessState(status)).toBe(expected);
  });

  it("lets an explicit outdated lifecycle override every backend status", () => {
    expect(pathReadinessState("passed", "outdated")).toBe("outdated");
    expect(environmentReadinessState("available", "outdated")).toBe("outdated");
    expect(sourceReadinessState("accepted", "outdated")).toBe("outdated");
    expect(preflightReadinessState("passed", "outdated")).toBe("outdated");
  });

  it.each(["waiting", "running", "unavailable"] as const)("uses explicit %s lifecycle state", (state) => {
    expect(pathReadinessState("passed", state)).toBe(state);
    expect(environmentReadinessState("available", state)).toBe(state);
    expect(sourceReadinessState("accepted", state)).toBe(state);
    expect(preflightReadinessState("passed", state)).toBe(state);
  });
});

describe("buildSourceReviewSummary", () => {
  it("uses returned source and path evidence without inventing a builder name", () => {
    expect(buildSourceReviewSummary(sourceAnalysis, pathValidation)).toEqual({
      angularVersion: "20.2.4",
      workspaceTopology: "nx-monorepo",
      packageManager: "npm",
      projectCount: "2",
      builderName: unavailable,
      customBuilderDetected: "Yes",
      lockfile: "package-lock.json",
      evidenceConfidence: "high",
      reservedTarget: "C:/external/target/source-angular-21",
      warnings: ["CUSTOM_BUILDER_REVIEW_REQUIRED"],
    });
  });

  it.each([
    [{ resolved: "20.2.4", declared: "^20.2.0", family: "20.x" }, "20.2.4"],
    [{ resolved: null, declared: "^20.2.0", family: "20.x" }, "^20.2.0"],
    [{ resolved: null, declared: null, family: "20.x" }, "20.x"],
  ])("prefers resolved, then declared, then family Angular version evidence", (version, expected) => {
    const analysis = {
      ...sourceAnalysis,
      snapshot: {
        ...sourceAnalysis.snapshot,
        versions: [{ package: "@angular/core", confidence: "medium", ...version }],
      },
    } as SourceAnalysisResult;
    expect(buildSourceReviewSummary(analysis, pathValidation).angularVersion).toBe(expected);
  });

  it("uses explicit unavailable fallbacks when readiness evidence is missing", () => {
    const analysis = {
      ...sourceAnalysis,
      snapshot: {
        ...sourceAnalysis.snapshot,
        package_manager: "",
        lockfile: null,
        versions: [],
        topology: { projects: [], libraries: [], is_nx: false, has_custom_builder: false, classification: "" },
        warnings: [],
      },
    } as SourceAnalysisResult;

    expect(buildSourceReviewSummary(analysis, null)).toEqual({
      angularVersion: unavailable,
      workspaceTopology: unavailable,
      packageManager: unavailable,
      projectCount: "0",
      builderName: unavailable,
      customBuilderDetected: "No",
      lockfile: unavailable,
      evidenceConfidence: unavailable,
      reservedTarget: unavailable,
      warnings: [],
    });
  });

  it("does not infer that a custom builder is absent without source analysis", () => {
    expect(buildSourceReviewSummary(null, pathValidation).customBuilderDetected).toBe(unavailable);
  });
});
