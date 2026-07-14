import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MigrationSetupForm } from "@/components/MigrationSetupForm";
import { createMockMigration, validatePaths, validatePreflight } from "@/api/migrations";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push })
}));

vi.mock("@/api/migrations", () => ({
  validatePaths: vi.fn(),
  validatePreflight: vi.fn(),
  createMockMigration: vi.fn()
}));

describe("MigrationSetupForm", () => {
  beforeEach(() => {
    vi.mocked(validatePaths).mockReset();
    vi.mocked(validatePaths).mockResolvedValue({
      snapshot: { validation_id: "path-1", captured_at: new Date().toISOString(), policy_version: "path-validation-v1", status: "passed", source_path: "source", target_output_path: "target", source_fingerprint: "sha256:source", rules: [], blockers: [], warnings: [], target_reservation_eligible: true, checksum: "sha256:path" }
    });
    vi.mocked(validatePreflight).mockReset();
    vi.mocked(createMockMigration).mockReset();
    push.mockReset();
  });

  it("keeps start disabled until the current inputs have a passed preflight", async () => {
    vi.mocked(validatePreflight).mockResolvedValue({
      preflight_id: "preflight-1",
      checksum: "sha256:preflight",
      expires_at: new Date(Date.now() + 60000).toISOString(),
      source_path: "source",
      target_output_path: "target",
      status: "passed",
      message: "passed",
      blockers: [],
      warnings: [],
      capabilities: { python: "SUCCEEDED" },
      runtime_profile_available: true,
      registry_access: "placeholder_not_checked",
      topology_status: "placeholder_not_scanned",
      angular_eligibility: "placeholder_not_scanned",
      artifact: { artifact_id: "artifact-preflight", run_id: "preflight-1", stage_id: null, artifact_type: "json", relative_path: "00_job_setup/preflight-result.json", created_at: new Date().toISOString(), checksum: "sha256:artifact" }
    });
    vi.mocked(createMockMigration).mockResolvedValue({ run_id: "mock-run-angular-18-to-21" } as never);
    render(<MigrationSetupForm />);

    const start = screen.getByRole("button", { name: "Start" });
    expect(start).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Source path"), { target: { value: "source" } });
    fireEvent.change(screen.getByLabelText("Target output path"), { target: { value: "target" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    await screen.findAllByText("passed");
    expect(screen.getByRole("link", { name: "Open preflight artifact" })).toHaveAttribute("href", "http://127.0.0.1:8000/api/v1/artifacts/artifact-preflight");

    expect(screen.getByRole("link", { name: "Open preflight artifact" })).toHaveAttribute("href", "http://127.0.0.1:8000/api/v1/artifacts/artifact-preflight");

    expect(start).toBeEnabled();

    fireEvent.change(screen.getByLabelText("Target output path"), { target: { value: "changed-target" } });
    expect(start).toBeDisabled();
  });

  it("starts with the validated checksum", async () => {
    vi.mocked(validatePreflight).mockResolvedValue({
      preflight_id: "preflight-1",
      checksum: "sha256:preflight",
      expires_at: new Date(Date.now() + 60000).toISOString(),
      source_path: "source",
      target_output_path: "target",
      status: "passed_with_warnings",
      message: "passed",
      blockers: [],
      warnings: ["placeholder"],
      capabilities: {},
      runtime_profile_available: true,
      registry_access: "placeholder_not_checked",
      topology_status: "placeholder_not_scanned",
      angular_eligibility: "placeholder_not_scanned",
      artifact: null
    });
    vi.mocked(createMockMigration).mockResolvedValue({ run_id: "mock-run-angular-18-to-21" } as never);
    render(<MigrationSetupForm />);

    fireEvent.change(screen.getByLabelText("Source path"), { target: { value: "source" } });
    fireEvent.change(screen.getByLabelText("Target output path"), { target: { value: "target" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByText("passed_with_warnings");
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    await waitFor(() => expect(createMockMigration).toHaveBeenCalledWith({ preflight_checksum: "sha256:preflight" }));
    expect(push).toHaveBeenCalledWith("/migrations/mock-run-angular-18-to-21");
  });
});
