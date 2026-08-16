import type { ReactNode } from "react";
import type { AssistantMessage as AssistantMessageData } from "@/types/assistant";

const stageRoute = /angular-(\d+)(?:\.x)?-to-(\d+)(?:\.x)?(?:--[a-z0-9-]+)?/i;

export function displayAssistantStage(value: string): string {
  const text = value?.trim() ?? "";
  const match = stageRoute.exec(text);
  if (match) return `Angular ${match[1]} → ${match[2]}`;
  const readable = text.replace(/^G\d+\s+/i, "");
  return !readable || readable === "unknown" || readable.includes("--") ? "Current migration stage" : readable;
}

export function displayAssistantPhase(value: string): string {
  const text = value?.trim() ?? "";
  return !text || text === "unknown" ? "Current phase" : text.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function displayAssistantGate(value: string): string {
  const text = value?.trim() ?? "";
  const match = /\bG\d+\b\s*(pending|approved|rejected)?/i.exec(text);
  if (!match) return !text || text === "unknown" ? "Human review status unavailable" : text;
  const status = match[1]?.toLowerCase();
  return status === "pending" ? "Human review pending" : status === "approved" ? "Human review approved" : status === "rejected" ? "Human review rejected" : "Human review required";
}

export function displayAssistantBlocker(value: string, status: string): string {
  const text = value?.trim() ?? "";
  if (!text || ["none", "unknown", "unavailable"].includes(text.toLowerCase())) return "No current blocker";
  if (status.toUpperCase() === "COMPLETED") return "No current blocker; earlier failures are historical";
  return text.replace(/\bG\d+\b/gi, "the relevant human review");
}

export function displayAssistantAction(value: string): string {
  const text = value?.trim() ?? "";
  if (!text || text === "unknown") return "Next permitted action unavailable";
  return text.replace(/\bG\d+\b/gi, "the current human review");
}

function inlineMarkdown(value: string): ReactNode[] {
  return value.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*")) return <em key={index}>{part.slice(1, -1)}</em>;
    return <span key={index}>{part}</span>;
  });
}

function markdownBlocks(answer: string): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = answer.replace(/\r\n?/g, "\n").split("\n");
  let paragraph: string[] = [];
  let list: string[] = [];
  let ordered = false;
  let code: string[] | null = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push(<p key={`p-${blocks.length}`}>{inlineMarkdown(paragraph.join("\n"))}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    const items = list.map((item, index) => <li key={index}>{inlineMarkdown(item)}</li>);
    blocks.push(ordered ? <ol key={`ol-${blocks.length}`}>{items}</ol> : <ul key={`ul-${blocks.length}`}>{items}</ul>);
    list = [];
  };

  lines.forEach((line) => {
    if (line.trim().startsWith("```") || code !== null) {
      if (line.trim().startsWith("```") && code !== null) {
        blocks.push(<pre key={`code-${blocks.length}`}><code>{code.join("\n")}</code></pre>);
        code = null;
      } else if (code !== null) code.push(line);
      else code = [];
      flushParagraph();
      flushList();
      return;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    const bullet = /^\s*[-*]\s+(.+)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (!line.trim()) { flushParagraph(); flushList(); return; }
    if (heading) { flushParagraph(); flushList(); blocks.push(<h3 key={`h-${blocks.length}`}>{inlineMarkdown(heading[2])}</h3>); return; }
    if (bullet || numbered) {
      flushParagraph();
      const nextOrdered = Boolean(numbered);
      if (list.length && ordered !== nextOrdered) flushList();
      ordered = nextOrdered;
      list.push((bullet ?? numbered)![1]);
      return;
    }
    flushList();
    paragraph.push(line);
  });
  const unfinishedCode = code as string[] | null;
  if (unfinishedCode) blocks.push(<pre key={`code-${blocks.length}`}><code>{unfinishedCode.join("\n")}</code></pre>);
  flushParagraph();
  flushList();
  return blocks;
}

export function AssistantMessage({ message: rawMessage }: { message: AssistantMessageData }) {
  const message = { ...rawMessage, current_phase: displayAssistantPhase(rawMessage.current_phase), current_stage: displayAssistantStage(rawMessage.current_stage), current_gate: displayAssistantGate(rawMessage.current_gate), current_blocker: displayAssistantBlocker(rawMessage.current_blocker, rawMessage.workflow_status), next_permitted_action: displayAssistantAction(rawMessage.next_permitted_action) };
  const context = [message.current_phase, message.current_stage, message.current_gate].filter((value) => Boolean(value) && value !== "unknown").join(" · ");
  const state = message.semantic_state_version ?? message.workflow_state_version;
  const provenance = message.role === "assistant" && state > 0
    ? `Based on state ${state}${message.current_stage && message.current_stage !== "unknown" ? ` · ${message.current_stage}` : ""}`
    : "";
  const footer = [context, provenance, message.stale ? "stale answer" : ""].filter(Boolean).join(" · ");
  return <article data-role={message.role} aria-label={`${message.role} message`}>
    <small>{message.role}</small>
    {message.role === "assistant" ? markdownBlocks(message.answer) : <p>{message.answer}</p>}
    {footer ? <small>{footer}</small> : null}
  </article>;
}
