import type { AssistantMessage } from "@/types/assistant";

export type AssistantLifecycleEvent = { event_id?: string; sequence: number; event_type: string; message_id?: string; payload?: unknown };

export function assistantReplayDecision(lastSequence: number, event: AssistantLifecycleEvent): "ignore" | "apply" | "gap" {
  if (event.sequence <= lastSequence) return "ignore";
  // Assistant lifecycle sequence is contiguous in its own durable table;
  // workflow_events use a separate global sequence and must not affect this.
  if (event.sequence > lastSequence + 1) return "gap";
  return "apply";
}

export function replaceAssistantHistory(_current: AssistantMessage[], restored: AssistantMessage[]): AssistantMessage[] {
  return [...restored].sort((left, right) => left.message_order - right.message_order);
}
