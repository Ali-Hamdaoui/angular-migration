import type { AssistantMessage as AssistantMessageData } from "@/types/assistant";

export function AssistantMessage({ message }: { message: AssistantMessageData }) {
  return <article data-role={message.role} aria-label={`${message.role} message`}>
    <small>{message.role}</small><p>{message.answer}</p>
    <small>{message.current_phase} · {message.current_stage} · {message.current_gate}{message.stale ? " · stale answer" : ""}</small>
  </article>;
}
