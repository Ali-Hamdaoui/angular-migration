import { assistantReplayDecision, replaceAssistantHistory } from "@/components/assistantReplay";

describe("assistant lifecycle replay", () => {
  it("ignores duplicates and detects sequence gaps", () => {
    expect(assistantReplayDecision(4, { sequence: 4, event_type: "ASSISTANT_RESPONSE_COMPLETED" })).toBe("ignore");
    expect(assistantReplayDecision(4, { sequence: 6, event_type: "ASSISTANT_RESPONSE_COMPLETED" })).toBe("gap");
    expect(assistantReplayDecision(4, { sequence: 5, event_type: "ASSISTANT_RESPONSE_STARTED" })).toBe("apply");
  });
  it("replaces restored history instead of appending replay duplicates", () => {
    const message = (id: string, order: number) => ({ message_id: id, message_order: order } as never);
    expect(replaceAssistantHistory([message("old", 1)], [message("m2", 2), message("m1", 1)]).map((item) => item.message_id)).toEqual(["m1", "m2"]);
  });
});
