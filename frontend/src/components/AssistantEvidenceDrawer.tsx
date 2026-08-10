import type { AssistantEvidence } from "@/types/assistant";
import { getBackendBaseUrl } from "@/api/client";

export function AssistantEvidenceDrawer({ citations }: { citations: AssistantEvidence[] }) {
  if (!citations.length) return null;
  return <details aria-label="Validated evidence"><summary>Evidence <span className="srOnly">({citations.length})</span></summary><ul>{citations.map((item) => <li key={item.excerpt_id ?? `${item.artifact_id}:${item.checksum}`}><a href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(item.artifact_id)}`} target="_blank" rel="noreferrer">{item.label}</a><small> {item.checksum_sha256 ?? item.checksum}{item.locator ? ` · ${item.locator.kind}:${item.locator.value}` : ""}</small></li>)}</ul></details>;
}
