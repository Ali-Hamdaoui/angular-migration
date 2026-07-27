import type { AssistantEvidence } from "@/types/assistant";
import { getBackendBaseUrl } from "@/api/client";

export function AssistantEvidenceDrawer({ evidence }: { evidence: AssistantEvidence[] }) {
  if (!evidence.length) return null;
  return <details aria-label="Validated evidence"><summary>Validated evidence ({evidence.length})</summary><ul>{evidence.map((item) => <li key={`${item.artifact_id}:${item.checksum}`}><a href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(item.artifact_id)}`} target="_blank" rel="noreferrer">{item.label}</a><small> {item.checksum}{item.excerpt_locator ? ` · ${item.excerpt_locator}` : ""}</small></li>)}</ul></details>;
}
