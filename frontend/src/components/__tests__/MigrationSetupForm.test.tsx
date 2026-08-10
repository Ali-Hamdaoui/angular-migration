import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MigrationSetupForm } from "@/components/MigrationSetupForm";
import { analyzeSource, refreshEnvironment, validatePaths } from "@/api/migrations";
import { createProductionPreflight } from "@/api/preflights";
import { ApiClientError } from "@/api/client";
import type { ProductionPreflight } from "@/types/preflight";

const push = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/api/migrations", () => ({
  validatePaths: vi.fn(),
  refreshEnvironment: vi.fn(),
  analyzeSource: vi.fn(),
}));
vi.mock("@/api/preflights", () => ({ createProductionPreflight: vi.fn() }));

const now = "2026-08-09T10:00:00Z";
const expires = "2099-08-09T11:00:00Z";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function pathResult(
  id = "path-1",
  status: "passed" | "passed_with_warnings" | "blocked" = "passed",
  eligible = true,
) {
  return {
    snapshot: {
      validation_id: id,
      captured_at: now,
      policy_version: "path-validation-v2-external-output",
      status,
      source_path: "C:/external/source",
      target_parent_path: "C:/external/target",
      generated_output_name: "source-angular-21",
      resolved_output_root: "C:/external/target/source-angular-21",
      reservation_id: "reservation-1",
      reservation_expires_at: expires,
      target_output_path: "C:/external/target/source-angular-21",
      source_fingerprint: "sha256:source",
      rules: [],
      blockers: status === "blocked" ? ["TARGET_PARENT_INSIDE_SOURCE"] : [],
      warnings: status === "passed_with_warnings" ? ["SOURCE_OUTSIDE_ALLOWED_ROOTS"] : [],
      target_reservation_eligible: eligible,
      checksum: `sha256:${id}`,
    },
  };
}

function environmentResult(id = "environment-1", status: "available" | "degraded" | "blocked" = "available") {
  return {
    snapshot: {
      snapshot_id: id,
      captured_at: now,
      policy_version: "environment-capability-v1",
      status,
      runtimes: [],
      node_npm_npx_paired: true,
      git_ready: true,
      python_ready: true,
      storage: {
        database_path: "C:/platform/state.db",
        artifact_root: "C:/platform/artifacts",
        writable: true,
        local_filesystem: true,
        free_bytes: 1024,
        status: "available" as const,
      },
      network: {
        registry_configured: true,
        proxy_configured: false,
        https_proxy_configured: false,
        strict_ssl: true,
        custom_ca_configured: false,
        credentials_redacted: true,
      },
      blockers: status === "blocked" ? ["GIT_NOT_AVAILABLE"] : [],
      warnings: status === "degraded" ? ["REGISTRY_NOT_CONFIRMED"] : [],
      checksum: `sha256:${id}`,
    },
    artifact: null,
  };
}

function analysisResult(id = "analysis-1", status: "accepted" | "review_required" | "blocked" = "accepted") {
  return {
    snapshot: {
      analysis_id: id,
      policy_version: "source-analysis-v1",
      status,
      source_path: "C:/external/source",
      package_manager: "npm",
      lockfile: "package-lock.json",
      versions: [
        { package: "@angular/core", declared: "^20.2.0", resolved: "20.2.4", family: "20.x", confidence: "high" as const },
      ],
      topology: {
        projects: ["portal", "admin"],
        libraries: ["ui"],
        is_nx: true,
        has_custom_builder: true,
        classification: "nx-monorepo",
      },
      blockers: status === "blocked" ? ["SOURCE_VERSION_BLOCKED"] : [],
      warnings: status === "review_required" ? ["CUSTOM_BUILDER_REVIEW_REQUIRED"] : [],
      checksum: `sha256:${id}`,
    },
  };
}

function preflight(
  status: ProductionPreflight["snapshot"]["status"],
  id = "preflight-1",
  blockers: string[] = [],
  warnings: string[] = [],
): ProductionPreflight {
  return {
    snapshot: {
      preflight_id: id,
      gate_id: "G01",
      gate_version: "s1-g01-v1",
      state_version: 1,
      status,
      approval_status: status === "expired" ? "expired" : status === "stale" ? "stale" : "pending",
      created_at: now,
      expires_at: expires,
      input_checksum: `sha256:input-${id}`,
      artifact_set_checksum: `sha256:evidence-${id}`,
      target_angular_family: "21.x",
      migration_mode: "strict-functional-parity",
      source_path: "C:/external/source",
      target_parent_path: "C:/external/target",
      generated_output_name: "source-angular-21",
      resolved_output_root: "C:/external/target/source-angular-21",
      platform_repository_root: "C:/platform/angular-migration",
      target_output_path: "C:/external/target/source-angular-21",
      target_reservation_id: "reservation-1",
      blockers,
      warnings,
      artifacts: {
        "preflight_result.json": {
          artifact_id: `artifact-${id}`,
          checksum: `sha256:artifact-${id}`,
          relative_path: "00_job_setup/preflight_result.json",
        },
      },
      decision_history: [],
    },
  };
}

function fillProject(source = "C:/external/source", target = "C:/external/target") {
  fireEvent.change(screen.getByLabelText("Source path"), { target: { value: source } });
  fireEvent.change(screen.getByLabelText("External target-parent path"), { target: { value: target } });
}

function checkReadiness() {
  fireEvent.click(screen.getByRole("button", { name: /Check readiness/ }));
}

function operationRow(name: string) {
  return screen.getByRole("listitem", { name });
}

describe("MigrationSetupForm", () => {
  beforeEach(() => {
    vi.mocked(validatePaths).mockReset();
    vi.mocked(refreshEnvironment).mockReset();
    vi.mocked(analyzeSource).mockReset();
    vi.mocked(createProductionPreflight).mockReset();
    push.mockReset();
    vi.mocked(validatePaths).mockResolvedValue(pathResult());
    vi.mocked(refreshEnvironment).mockResolvedValue(environmentResult());
    vi.mocked(analyzeSource).mockResolvedValue(analysisResult());
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("passed"));
  });

  it("shows the four-step journey, four waiting operations, and the initial action", () => {
    render(<MigrationSetupForm />);

    const journey = screen.getByRole("list", { name: "Migration preparation steps" });
    expect(within(journey).getAllByRole("listitem")).toHaveLength(4);
    expect(within(journey).getByText("Project")).toBeInTheDocument();
    expect(within(journey).getByText("Readiness")).toBeInTheDocument();
    expect(within(journey).getByText("Source review")).toBeInTheDocument();
    expect(within(journey).getByText("Create run")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check readiness" })).toBeEnabled();
    for (const label of [
      "Path safety and target reservation",
      "Environment capability",
      "Source analysis",
      "Production preflight",
    ]) {
      expect(within(operationRow(label)).getByText("Waiting")).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "Review production readiness" })).not.toBeInTheDocument();
  });

  it("shows path running first, then starts environment and source together", async () => {
    const path = deferred<ReturnType<typeof pathResult>>();
    const environment = deferred<ReturnType<typeof environmentResult>>();
    const source = deferred<ReturnType<typeof analysisResult>>();
    vi.mocked(validatePaths).mockReturnValue(path.promise);
    vi.mocked(refreshEnvironment).mockReturnValue(environment.promise);
    vi.mocked(analyzeSource).mockReturnValue(source.promise);
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    expect(within(operationRow("Path safety and target reservation")).getByText("Running")).toBeInTheDocument();
    expect(within(operationRow("Environment capability")).getByText("Waiting")).toBeInTheDocument();
    expect(within(operationRow("Source analysis")).getByText("Waiting")).toBeInTheDocument();
    expect(refreshEnvironment).not.toHaveBeenCalled();
    expect(analyzeSource).not.toHaveBeenCalled();

    path.resolve(pathResult());
    await waitFor(() => expect(refreshEnvironment).toHaveBeenCalledTimes(1));
    expect(analyzeSource).toHaveBeenCalledTimes(1);
    expect(within(operationRow("Path safety and target reservation")).getByText("Passed")).toBeInTheDocument();
    expect(within(operationRow("Environment capability")).getByText("Running")).toBeInTheDocument();
    expect(within(operationRow("Source analysis")).getByText("Running")).toBeInTheDocument();
    expect(createProductionPreflight).not.toHaveBeenCalled();

    environment.resolve(environmentResult());
    source.resolve(analysisResult());
    await waitFor(() => expect(createProductionPreflight).toHaveBeenCalledTimes(1));
  });

  it("binds one successful chain and hands off to its existing G01 route", async () => {
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    expect(await screen.findByText("Readiness checks passed")).toBeInTheDocument();
    expect(createProductionPreflight).toHaveBeenCalledWith(expect.objectContaining({
      path_validation_id: "path-1",
      environment_snapshot_id: "environment-1",
      source_analysis_id: "analysis-1",
    }));
    expect(screen.getByText("20.2.4")).toBeInTheDocument();
    expect(screen.getByText("nx-monorepo")).toBeInTheDocument();
    expect(screen.getByText("Not available from readiness evidence")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review production readiness" }));
    expect(push).toHaveBeenCalledWith("/preflights/preflight-1");
    expect(screen.queryByRole("button", { name: "Create authoritative run" })).not.toBeInTheDocument();
  });

  it("keeps warning evidence visible while permitting G01 review", async () => {
    vi.mocked(validatePaths).mockResolvedValue(pathResult("path-1", "passed_with_warnings"));
    vi.mocked(refreshEnvironment).mockResolvedValue(environmentResult("environment-1", "degraded"));
    vi.mocked(analyzeSource).mockResolvedValue(analysisResult("analysis-1", "review_required"));
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("passed_with_warnings", "preflight-warning", [], ["WORKSPACE_TOPOLOGY_UNKNOWN"]));
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    expect(await screen.findByText("Readiness checks completed with warnings")).toBeInTheDocument();
    expect(within(operationRow("Path safety and target reservation")).getByText("Warning")).toBeInTheDocument();
    expect(within(operationRow("Environment capability")).getByText("Warning")).toBeInTheDocument();
    expect(within(operationRow("Source analysis")).getByText("Warning")).toBeInTheDocument();
    expect(within(operationRow("Source analysis")).getByText("CUSTOM_BUILDER_REVIEW_REQUIRED")).toBeInTheDocument();
    expect(within(operationRow("Production preflight")).getByText("Warning")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review production readiness" })).toBeEnabled();
  });

  it.each([
    ["blocked preflight", () => preflight("blocked", "preflight-blocked", ["RUNTIME_BLOCKED"])],
    ["expired preflight", () => preflight("expired", "preflight-expired")],
    ["stale preflight", () => preflight("stale", "preflight-stale")],
  ])("withholds review for a %s", async (_name, result) => {
    vi.mocked(createProductionPreflight).mockResolvedValue(result());
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    await waitFor(() => expect(createProductionPreflight).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("button", { name: "Review production readiness" })).not.toBeInTheDocument();
  });

  it.each([
    ["blocked", true],
    ["passed", false],
  ] as const)("withholds review for a %s or ineligible path result", async (status, eligible) => {
    vi.mocked(validatePaths).mockResolvedValue(pathResult("path-blocked", status, eligible));
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    expect(await screen.findByText("Readiness checks are blocked")).toBeInTheDocument();
    expect(createProductionPreflight).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Review production readiness" })).not.toBeInTheDocument();
  });

  it.each([
    ["Environment capability", "environment", new ApiClientError("Backend request failed", 503, "POST", "/environment/refresh", '{"error_code":"environment_unavailable"}')],
    ["Source analysis", "source", new ApiClientError("Backend request failed", 502, "POST", "/sources/analyze", '{"error_code":"analysis_unavailable"}')],
  ])("shows a successful sibling and an unavailable %s without calling production", async (rowLabel, rejectedRequest, requestError) => {
    if (rejectedRequest === "environment") vi.mocked(refreshEnvironment).mockRejectedValue(requestError);
    else vi.mocked(analyzeSource).mockRejectedValue(requestError);
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    expect(await screen.findByRole("alert")).toHaveTextContent("Readiness request failed");
    expect(within(operationRow(rowLabel)).getByText("Unavailable")).toBeInTheDocument();
    const sibling = rejectedRequest === "environment" ? "Source analysis" : "Environment capability";
    expect(within(operationRow(sibling)).getByText("Passed")).toBeInTheDocument();
    expect(createProductionPreflight).not.toHaveBeenCalled();
  });

  it("rejects an invalid production response and recovers on an explicit recheck", async () => {
    const invalidPreflight = preflight("passed", "preflight-invalid");
    delete (invalidPreflight.snapshot as Partial<ProductionPreflight["snapshot"]>).decision_history;
    vi.mocked(createProductionPreflight)
      .mockResolvedValueOnce(invalidPreflight)
      .mockResolvedValueOnce(preflight("passed", "preflight-recovered"));
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    expect(await screen.findByRole("alert")).toHaveTextContent("Production preflight is unavailable");
    expect(within(operationRow("Production preflight")).getByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review production readiness" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check readiness again" }));
    expect(await screen.findByText("Readiness checks passed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review production readiness" }));
    expect(push).toHaveBeenCalledWith("/preflights/preflight-recovered");
  });

  it("invalidates every identifier immediately when a Project value changes", async () => {
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();

    await screen.findByText("Readiness checks passed");
    fireEvent.change(screen.getByLabelText("Source path"), {
      target: { value: "C:/external/changed-source" },
    });
    expect(screen.getByRole("status")).toHaveTextContent("Configuration changed");
    expect(screen.getByRole("button", { name: "Check readiness again" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Review production readiness" })).not.toBeInTheDocument();
    expect(within(operationRow("Production preflight")).getByText("Outdated")).toBeInTheDocument();
  });

  it("discards a deferred old-revision result after an edit", async () => {
    const firstPath = deferred<ReturnType<typeof pathResult>>();
    vi.mocked(validatePaths).mockReturnValueOnce(firstPath.promise).mockResolvedValueOnce(pathResult("path-2"));
    vi.mocked(refreshEnvironment).mockResolvedValueOnce(environmentResult("environment-2"));
    vi.mocked(analyzeSource).mockResolvedValueOnce(analysisResult("analysis-2"));
    vi.mocked(createProductionPreflight).mockResolvedValueOnce(preflight("passed", "preflight-2"));
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();
    expect(within(operationRow("Path safety and target reservation")).getByText("Running")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Source path"), { target: { value: "C:/external/changed-source" } });
    expect(screen.getByRole("button", { name: "Check readiness again" })).toBeEnabled();
    firstPath.resolve(pathResult("path-old"));
    await Promise.resolve();
    expect(refreshEnvironment).not.toHaveBeenCalled();
    expect(screen.queryByText("Readiness checks passed")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review production readiness" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Check readiness again" }));
    await screen.findByText("Readiness checks passed");
    fireEvent.click(screen.getByRole("button", { name: "Review production readiness" }));
    expect(push).toHaveBeenCalledWith("/preflights/preflight-2");
  });

  it("uses only the second chain identifiers and operation scope on recheck", async () => {
    vi.mocked(validatePaths)
      .mockResolvedValueOnce(pathResult("path-1"))
      .mockResolvedValueOnce(pathResult("path-2"));
    vi.mocked(refreshEnvironment)
      .mockResolvedValueOnce(environmentResult("environment-1"))
      .mockResolvedValueOnce(environmentResult("environment-2"));
    vi.mocked(analyzeSource)
      .mockResolvedValueOnce(analysisResult("analysis-1"))
      .mockResolvedValueOnce(analysisResult("analysis-2"));
    vi.mocked(createProductionPreflight)
      .mockResolvedValueOnce(preflight("passed", "preflight-1"))
      .mockResolvedValueOnce(preflight("passed", "preflight-2"));
    render(<MigrationSetupForm />);
    fillProject();
    checkReadiness();
    await screen.findByText("Readiness checks passed");
    const firstPathKey = vi.mocked(validatePaths).mock.calls[0][0].idempotency_key;

    fireEvent.change(screen.getByLabelText("Source path"), { target: { value: "C:/external/changed-source" } });
    fireEvent.click(screen.getByRole("button", { name: "Check readiness again" }));
    await waitFor(() => expect(createProductionPreflight).toHaveBeenCalledTimes(2));

    expect(createProductionPreflight).toHaveBeenLastCalledWith(expect.objectContaining({
      path_validation_id: "path-2",
      environment_snapshot_id: "environment-2",
      source_analysis_id: "analysis-2",
    }));
    const secondPathKey = vi.mocked(validatePaths).mock.calls[1][0].idempotency_key;
    expect(secondPathKey).not.toBe(firstPathKey);
  });
});
