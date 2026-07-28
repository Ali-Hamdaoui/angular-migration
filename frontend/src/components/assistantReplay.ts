import type { AssistantMessage } from "@/types/assistant";

export type AssistantLifecycleEvent = { sequence: number; event_type: string; message_id?: string };

export function assistantReplayDecision(lastSequence: number, event: AssistantLifecycleEvent): "ignore" | "apply" | "gap" {
  if (event.sequence <= lastSequence) return "ignore";
  if (event.sequence > lastSequence + 1) return "gap";
  return "apply";
}

export function replaceAssistantHistory(_current: AssistantMessage[], restored: AssistantMessage[]): AssistantMessage[] {
  return [...restored].sort((left, right) => left.message_order - right.message_order);
}
