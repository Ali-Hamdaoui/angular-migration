describe("requestRepairRevision", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("posts the known-good repair revision contract unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ attempt_id: "repair-4", status: "evidence_frozen", idempotent_replay: false }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000");
    vi.stubEnv("NEXT_PUBLIC_AUTHENTICATED_ACTOR", "control-tower");
    vi.resetModules();
    const body = {
      attempt_id: "repair-3",
      proposal_id: "proposal-3",
      base_checksum: `sha256:${"a".repeat(64)}`,
      instruction: "Handle empty values",
      idempotency_key: "revision-key",
    };
    const { requestRepairRevision } = await import("@/api/transformation");

    await requestRepairRevision("run/1", "repair/3", body);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/runs/run%2F1/transformation/repairs/repair%2F3/revisions",
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Authenticated-Actor": "control-tower",
        },
        cache: "no-store",
        body: JSON.stringify(body),
      },
    );
  });
});
