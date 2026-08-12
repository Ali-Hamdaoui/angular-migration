import type { AssistantEvidence } from "@/types/assistant";
import type { ArtifactRefDto } from "@/types/generated/api";
import { presentArtifact } from "@/presentation/artifacts";
import { getBackendBaseUrl } from "@/api/client";

export function AssistantEvidenceDrawer({ citations, artifacts = [] }: { citations: AssistantEvidence[]; artifacts?: ArtifactRefDto[] }) {
  if (!citations.length) return null;
  const registered = new Map(artifacts.map((artifact) => [artifact.artifact_id, presentArtifact(artifact)]));
  return <details aria-label="Validated evidence"><summary>Evidence <span className="srOnly">({citations.length})</span></summary><ul>{citations.map((item) => {
    const presentation = registered.get(item.artifact_id);
    return <li key={item.excerpt_id ?? `${item.artifact_id}:${item.checksum}`}><a href={`${getBackendBaseUrl()}/api/v1/artifacts/${encodeURIComponent(item.artifact_id)}`} target="_blank" rel="noreferrer">{presentation?.title ?? item.label}</a><small className="technicalDetails"> {item.checksum_sha256 ?? item.checksum}{item.locator ? ` · ${item.locator.kind}:${item.locator.value}` : ""}</small></li>;
  })}</ul></details>;
}
