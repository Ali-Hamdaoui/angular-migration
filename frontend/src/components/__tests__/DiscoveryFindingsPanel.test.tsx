import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { getDiscovery } from "@/api/discovery";
import { DiscoveryFindingsPanel } from "@/components/DiscoveryFindingsPanel";

vi.mock("@/api/discovery", () => ({ getDiscovery: vi.fn() }));
const evidence = { run_id: "run-1", discovery_id: "discovery-1", status: "completed", scanner_results: [{ scanner: "workspace", status: "completed", findings: [{ key: "topology", value: "single_application_cli_workspace", confidence: "high", source_references: ["angular.json"] }], unknowns: [], warnings: [] }, { scanner: "dependencies", status: "unknown", findings: [], unknowns: ["PACKAGE_JSON_MISSING"], warnings: [] }], artifact_ids: ["artifact-workspace"], artifact_checksums: {}, prerequisite_artifact_ids: ["baseline"], state_version: 8, event_sequence: 12, idempotent_replay: false } as const;

describe("DiscoveryFindingsPanel", () => {
  it("renders authoritative facts, unknown markers, filtering, and safe artifact links", async () => {
    vi.mocked(getDiscovery).mockResolvedValue(evidence as never);
    render(<DiscoveryFindingsPanel runId="run-1" stateVersion={8} connectionStatus="open" />);
    expect(await screen.findByText('"single_application_cli_workspace"')).toBeInTheDocument();
    expect(screen.getByText("Unknown: PACKAGE_JSON_MISSING")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open artifact artifact-workspace" })).toHaveAttribute("href", "/api/v1/artifacts/artifact-workspace");
    fireEvent.change(screen.getByLabelText("Filter scanners"), { target: { value: "none" } });
    expect(screen.getByText("No discovery findings match this filter.")).toBeInTheDocument();
  });
  it("renders an empty authoritative state when discovery has not run", async () => {
    vi.mocked(getDiscovery).mockRejectedValue(new ApiClientError("not found", 404));
    render(<DiscoveryFindingsPanel runId="run-1" stateVersion={8} connectionStatus="open" />);
    expect(await screen.findByText("No authoritative discovery findings are available yet.")).toBeInTheDocument();
  });
  it("renders a readable backend failure without treating it as workflow progress", async () => {
    vi.mocked(getDiscovery).mockRejectedValue(new ApiClientError("unavailable", 500));
    render(<DiscoveryFindingsPanel runId="run-1" stateVersion={8} connectionStatus="reconnecting" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Discovery findings could not be loaded.");
  });
});
