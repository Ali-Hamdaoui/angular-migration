import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "@/api/client";
import {
  startAngularUpdate,
  getAngularUpdate,
  getTargetVersion,
  generateTransformationEvidence,
  getTransformationEvidence,
  getG08Approval,
  decideG08,
  completeAngularUpdate,
  verifyTargetVersion,
  getTargetVersionTyped,
  initializeG08,
} from "@/api/transformations";

const runId = "run-1";
const stageId = "stage-1";
const gateId = "G08";

describe("transformations API client", () => {
  it("startAngularUpdate posts to angular-update", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "running" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await startAngularUpdate(runId, stageId, {
      expected_state_version: 1, idempotency_key: "start-1", actor: "tester",
      source_version: "17.0.0", target_version: "18.0.0",
    }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/angular-update",
      expect.objectContaining({ method: "POST", body: expect.stringContaining("17.0.0") }),
    );
  });

  it("getAngularUpdate gets angular-update", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "running" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await getAngularUpdate(runId, stageId, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/angular-update",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("getTargetVersion gets target-version", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ target_version_status: "verified" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ target_version_status: "verified" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await getTargetVersion(runId, stageId, client);
    await getTargetVersionTyped(runId, stageId, client);

    expect(fetchMock).toHaveBeenNthCalledWith(1,
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/target-version",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(2,
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/target-version",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("generateTransformationEvidence posts to transformation-evidence", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ diff_checksum: "sha256:abc" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await generateTransformationEvidence(runId, stageId, {
      expected_state_version: 1, idempotency_key: "ev-1", actor: "tester",
      source_sandbox_path: "/src", target_sandbox_path: "/tgt",
    }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/transformation-evidence",
      expect.objectContaining({ method: "POST", body: expect.stringContaining("tgt") }),
    );
  });

  it("getTransformationEvidence gets transformation-evidence", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ diff_checksum: "sha256:abc" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await getTransformationEvidence(runId, stageId, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/transformation-evidence",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("getG08Approval gets the approval gate", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "pending" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await getG08Approval(runId, stageId, gateId, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/approvals/G08",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("decideG08 posts to decisions", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ decision: "approved" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await decideG08(runId, stageId, gateId, {
      expected_state_version: 1, idempotency_key: "g08-1", actor: "tester",
      decision: "approved", gate_id: "G08",
    }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/approvals/G08/decisions",
      expect.objectContaining({ method: "POST", body: expect.stringContaining("g08-1") }),
    );
  });

  it("completeAngularUpdate posts to angular-update/complete", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "succeeded" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await completeAngularUpdate(runId, stageId, {
      expected_state_version: 1, idempotency_key: "compl-1", actor: "tester", command_execution_id: "exec-1",
    }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/angular-update/complete",
      expect.objectContaining({ method: "POST", body: expect.stringContaining("compl-1") }),
    );
  });

  it("verifyTargetVersion posts to target-version/verify", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ target_version_status: "verified" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await verifyTargetVersion(runId, stageId, {
      expected_state_version: 1, idempotency_key: "ver-1", actor: "tester", command_execution_id: "exec-1",
    }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/target-version/verify",
      expect.objectContaining({ method: "POST", body: expect.stringContaining("ver-1") }),
    );
  });

  it("initializeG08 posts to package", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "pending" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await initializeG08(runId, stageId, gateId, {
      expected_state_version: 1, idempotency_key: "init-1", actor: "tester",
      decision: "approved", gate_id: "G08",
    }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run-1/stages/stage-1/approvals/G08/package",
      expect.objectContaining({ method: "POST", body: expect.stringContaining("init-1") }),
    );
  });

  it("encodes URI components in paths", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "running" }), { status: 200 }));
    const client = createApiClient("http://backend.test", fetchMock);

    await startAngularUpdate("run/1", "stage/1", {
      expected_state_version: 1, idempotency_key: "enc-1", actor: "tester",
      source_version: "17.0.0", target_version: "18.0.0",
    }, client);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://backend.test/api/v1/runs/run%2F1/stages/stage%2F1/angular-update",
      expect.any(Object),
    );
  });
});
