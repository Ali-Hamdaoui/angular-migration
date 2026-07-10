import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MigrationSetupForm } from "@/components/MigrationSetupForm";
import { validatePreflight } from "@/api/migrations";
import type { PreflightResultDto } from "@/types/generated/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock })
}));

vi.mock("@/api/migrations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/migrations")>()),
  validatePreflight: vi.fn()
}));

const preflightResult: PreflightResultDto = {
  run_id: "mock-run-angular-18-to-21",
  status: "passed",
  input_checksum: "sha256:test",
  expires_at: "2099-01-01T00:00:00Z",
  source_path: "C:/fixture",
  target_output_path: "C:/output/app",
  findings: [{ code: "RUNTIME_PROFILE_PLACEHOLDER", severity: "info", message: "Placeholder" }],
  capabilities: [],
  artifact: {
    artifact_id: "artifact-preflight",
    run_id: "mock-run-angular-18-to-21",
    stage_id: null,
    artifact_type: "json",
    relative_path: "00_job_setup/preflight-result.json",
    created_at: "2026-07-10T00:00:00Z",
    checksum: "sha256:artifact"
  }
};

describe("MigrationSetupForm", () => {
  beforeEach(() => {
    pushMock.mockReset();
    vi.mocked(validatePreflight).mockReset();
  });

  it("keeps Start disabled until a current passing preflight exists", async () => {
    vi.mocked(validatePreflight).mockResolvedValue(preflightResult);
    render(<MigrationSetupForm />);

    const start = screen.getByRole("button", { name: "Start Mock Migration" });
    expect(start).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Source path"), { target: { value: "C:/fixture" } });
    fireEvent.change(screen.getByLabelText("Target output path"), { target: { value: "C:/output/app" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate setup" }));

    await waitFor(() => expect(start).toBeEnabled());
    expect(screen.getByText("00_job_setup/preflight-result.json")).toBeInTheDocument();

    fireEvent.click(start);
    expect(pushMock).toHaveBeenCalledWith("/migrations/mock-run-angular-18-to-21");
  });

  it("invalidates Start when validated inputs change", async () => {
    vi.mocked(validatePreflight).mockResolvedValue(preflightResult);
    render(<MigrationSetupForm />);

    fireEvent.change(screen.getByLabelText("Source path"), { target: { value: "C:/fixture" } });
    fireEvent.change(screen.getByLabelText("Target output path"), { target: { value: "C:/output/app" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate setup" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Start Mock Migration" })).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Target output path"), { target: { value: "C:/output/app-v2" } });

    expect(screen.getByRole("button", { name: "Start Mock Migration" })).toBeDisabled();
    expect(screen.getByText(/Validate again before starting/)).toBeInTheDocument();
  });
});
