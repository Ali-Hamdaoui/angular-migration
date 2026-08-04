import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const now = new Date().toISOString();
const expires = new Date(Date.now() + 60_000).toISOString();

function preflight(status: "passed" | "passed_with_warnings" | "blocked", blockers: string[] = [], warnings: string[] = []): ProductionPreflight {
  return {
    snapshot: {
      preflight_id: "preflight-1", gate_id: "G01", gate_version: "s1-g01-v1", state_version: 1,
      status, approval_status: "pending", created_at: now, expires_at: expires,
      input_checksum: "sha256:input", artifact_set_checksum: "sha256:evidence",
      target_angular_family: "21.x", migration_mode: "strict-functional-parity",
      source_path: "C:/external/source", target_parent_path: "C:/external/target",
      generated_output_name: "source-angular-21", resolved_output_root: "C:/external/target/source-angular-21",
      platform_repository_root: "C:/platform/angular-migration", target_output_path: "C:/external/target/source-angular-21",
      target_reservation_id: "reservation-1", blockers, warnings,
      artifacts: { "preflight_result.json": { artifact_id: "artifact-preflight", checksum: "sha256:artifact", relative_path: "00_job_setup/preflight_result.json" } },
      decision_history: [],
    },
  };
}

describe("MigrationSetupForm", () => {
  beforeEach(() => {
    vi.mocked(validatePaths).mockReset();
    vi.mocked(refreshEnvironment).mockReset();
    vi.mocked(analyzeSource).mockReset();
    vi.mocked(createProductionPreflight).mockReset();
    push.mockReset();
    vi.mocked(validatePaths).mockResolvedValue({ snapshot: { validation_id: "path-1", captured_at: now, policy_version: "path-validation-v2-external-output", status: "passed", source_path: "C:/external/source", target_parent_path: "C:/external/target", generated_output_name: "source-angular-21", resolved_output_root: "C:/external/target/source-angular-21", reservation_id: "reservation-1", reservation_expires_at: expires, target_output_path: "C:/external/target/source-angular-21", source_fingerprint: "sha256:source", rules: [], blockers: [], warnings: [], target_reservation_eligible: true, checksum: "sha256:path" } });
    vi.mocked(refreshEnvironment).mockResolvedValue({ snapshot: { snapshot_id: "environment-1" } } as never);
    vi.mocked(analyzeSource).mockResolvedValue({ snapshot: { analysis_id: "analysis-1", status: "accepted", source_path: "C:/external/source", blockers: [], warnings: [] } });
  });

  function fillAndValidate() {
    fireEvent.change(screen.getByLabelText("Source application folder"), { target: { value: "C:/external/source" } });
    fireEvent.change(screen.getByLabelText("Output folder"), { target: { value: "C:/external/target" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate paths" }));
  }

  it("uses one durable validation chain and exposes only its authoritative passed result", async () => {
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("passed"));
    render(<MigrationSetupForm />);
    fillAndValidate();

    await screen.findByText("Validation ID: preflight-1");
    expect(validatePaths).toHaveBeenCalledTimes(1);
    expect(refreshEnvironment).toHaveBeenCalledTimes(1);
    expect(analyzeSource).toHaveBeenCalledWith(expect.objectContaining({ source_path: "C:/external/source" }));
    expect(createProductionPreflight).toHaveBeenCalledWith(expect.objectContaining({ path_validation_id: "path-1", environment_snapshot_id: "environment-1", source_analysis_id: "analysis-1" }));
    expect(screen.queryByLabelText("Path check result")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open validation evidence" })).toHaveAttribute("href", "http://127.0.0.1:8000/api/v1/artifacts/artifact-preflight");
    expect(screen.getByRole("button", { name: "Start migration" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Start migration" }));
    expect(push).toHaveBeenCalledWith("/preflights/preflight-1");
  });

  it("reads live form values and reports empty paths without disabling Validate", async () => {
    render(<MigrationSetupForm />);
    const validate = screen.getByRole("button", { name: "Validate paths" });
    expect(validate).toBeEnabled();
    fireEvent.click(validate);
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter both a source path and an external target-parent path.");
    expect(validatePaths).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Source application folder"), { target: { value: " C:/restored/source " } });
    fireEvent.change(screen.getByLabelText("Output folder"), { target: { value: " C:/restored/target " } });
    fireEvent.click(validate);
    await waitFor(() => expect(validatePaths).toHaveBeenCalledWith(expect.objectContaining({ source_path: "C:/restored/source", target_parent_path: "C:/restored/target" })));
  });

  it("restores DOM values, validates them, and binds Start to the resulting preflight", async () => {
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("passed"));
    render(<MigrationSetupForm />);
    const source = screen.getByLabelText("Source application folder") as HTMLInputElement;
    const target = screen.getByLabelText("Output folder") as HTMLInputElement;
    source.value = "C:/restored/source";
    target.value = "C:/restored/target";

    fireEvent.click(screen.getByRole("button", { name: "Validate paths" }));

    await screen.findByText("Validation ID: preflight-1");
    expect(validatePaths).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Start migration" })).toBeEnabled();
  });

  it("sends exactly one path-validation request for one Validate click", async () => {
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("passed"));
    render(<MigrationSetupForm />);
    fireEvent.change(screen.getByLabelText("Source application folder"), { target: { value: "C:/typed/source" } });
    fireEvent.change(screen.getByLabelText("Output folder"), { target: { value: "C:/typed/target" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate paths" }));

    await screen.findByText("Validation ID: preflight-1");
    expect(validatePaths).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Start migration" })).toBeEnabled();
  });

  it("invalidates Start when a path changes after a passed preflight", async () => {
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("passed"));
    render(<MigrationSetupForm />);
    fillAndValidate();
    await screen.findByText("Validation ID: preflight-1");
    expect(screen.getByRole("button", { name: "Start migration" })).toBeEnabled();
    fireEvent.input(screen.getByLabelText("Source application folder"), { target: { value: "C:/changed/source" } });
    expect(screen.getByRole("button", { name: "Start migration" })).toBeDisabled();
  });

  it("keeps Start disabled when the latest authoritative decision is blocked", async () => {
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("blocked", ["runtime_tool_unavailable_git"]));
    render(<MigrationSetupForm />);
    fillAndValidate();

    await screen.findByText(/runtime_tool_unavailable_git/);
    expect(screen.getByRole("button", { name: "Start migration" })).toBeDisabled();
    expect(screen.queryByText(/Reserved future output root/)).toBeInTheDocument();
  });

  it("allows warnings without converting the latest result into a blocker", async () => {
    vi.mocked(createProductionPreflight).mockResolvedValue(preflight("passed_with_warnings", [], ["WORKSPACE_TOPOLOGY_UNKNOWN"]));
    render(<MigrationSetupForm />);
    fillAndValidate();

    await screen.findByText(/WORKSPACE_TOPOLOGY_UNKNOWN/);
    await waitFor(() => expect(screen.getByRole("button", { name: "Start migration" })).toBeEnabled());
  });
  it("reports the failed secondary request without treating the path stage as a preflight", async () => {
    vi.mocked(refreshEnvironment).mockRejectedValue(new ApiClientError("Backend request failed", 503, "POST", "/environment/refresh", '{"error_code":"environment_unavailable"}'));
    render(<MigrationSetupForm />);
    fillAndValidate();

    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("environment and source analysis failed — POST /environment/refresh returned 503");
    expect(screen.getByRole("heading", { name: "Path check" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Migration readiness result")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start migration" })).toBeDisabled();
  });

  it("rejects an invalid production-preflight response and clears the error after a later success", async () => {
    vi.mocked(createProductionPreflight).mockResolvedValueOnce({} as ProductionPreflight).mockResolvedValueOnce(preflight("passed"));
    render(<MigrationSetupForm />);
    fillAndValidate();

    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("production preflight failed");
    fireEvent.click(screen.getByRole("button", { name: "Validate paths" }));
    await screen.findByText("Validation ID: preflight-1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start migration" })).toBeEnabled();
  });
});
