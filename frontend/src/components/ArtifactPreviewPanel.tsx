"use client";

import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { getArtifactById, type ArtifactContentResponse } from "@/api/migrations";
import type { ArtifactRefDto } from "@/types/generated/api";
import { presentArtifact, type ArtifactPresentation } from "@/presentation/artifacts";
import { StaticLogArtifactViewer } from "./LogViewer";
import { MarkdownReportViewer } from "./MarkdownReportViewer";
import { UnifiedDiffViewer } from "./UnifiedDiffViewer";
import styles from "./ControlTowerShell.module.css";

type ArtifactPreviewPanelProps = {
  artifact?: ArtifactRefDto;
  presentation?: ArtifactPresentation;
  initialContent?: string;
  initialCreatedBy?: string | null;
  loadArtifact?: (artifactId: string) => Promise<ArtifactContentResponse>;
  headingRef?: RefObject<HTMLHeadingElement | null>;
};

function attemptFromPath(path: string): string | null {
  return path.match(/attempt[-_/]?(\d+)/i)?.[0] ?? null;
}

function viewerFor(artifact: ArtifactRefDto, content: string) {
  if (artifact.artifact_type === "diff" || artifact.artifact_type === "patch" || artifact.relative_path.endsWith(".patch") || artifact.relative_path.endsWith(".diff")) {
    return <UnifiedDiffViewer content={content} />;
  }
  if (artifact.artifact_type === "markdown" || artifact.artifact_type === "report" || artifact.relative_path.endsWith(".md")) {
    return <MarkdownReportViewer content={content} />;
  }
  return <StaticLogArtifactViewer content={content} maxLines={200} />;
}

function artifactIdentity(artifact: ArtifactRefDto): string {
  return `${artifact.run_id}|${artifact.artifact_id}|${artifact.checksum}`;
}

function ArtifactPreviewContent({ artifact, presentation, initialContent, initialCreatedBy = null, loadArtifact = getArtifactById, headingRef }: ArtifactPreviewPanelProps & { artifact: ArtifactRefDto }) {
  const [content, setContent] = useState<string | null>(initialContent ?? null);
  const [createdBy, setCreatedBy] = useState<string | null>(initialCreatedBy);
  const [status, setStatus] = useState<"idle" | "loading" | "loaded" | "failed">(initialContent ? "loaded" : "idle");
  const attempt = useMemo(() => attemptFromPath(artifact.relative_path), [artifact.relative_path]);
  const presented = presentation ?? presentArtifact(artifact);
  const identity = useMemo(() => artifactIdentity(artifact), [artifact]);
  const identityRef = useRef(identity);
  const requestGeneration = useRef(0);

  useEffect(() => {
    identityRef.current = identity;
    requestGeneration.current += 1;
    setContent(initialContent ?? null);
    setCreatedBy(initialCreatedBy);
    setStatus(initialContent ? "loaded" : "idle");
  }, [identity, initialContent, initialCreatedBy]);

  async function openArtifact() {
    if (status === "loading") return;
    const generation = ++requestGeneration.current;
    const requestedIdentity = identity;
    setStatus("loading");
    try {
      const response = await loadArtifact(artifact.artifact_id);
      const responseIdentity = response.artifact
        ? artifactIdentity(response.artifact)
        : "";
      if (generation !== requestGeneration.current || identityRef.current !== requestedIdentity) {
        return;
      }
      if (responseIdentity !== requestedIdentity) {
        setContent(null);
        setCreatedBy(null);
        setStatus("failed");
        return;
      }
      setContent(response.content);
      setCreatedBy(response.created_by);
      setStatus("loaded");
    } catch {
      setStatus("failed");
    }
  }

  return (
    <article className={styles.previewPanel}>
      <div className={styles.previewHeader}>
        <div>
          <h3 ref={headingRef} tabIndex={-1}>{presented.title}</h3>
          <p className={styles.note}>{presented.stageLabel} · {presented.category}{presented.attemptLabel ? ` · ${presented.attemptLabel}` : ""}</p>
        </div>
        <button type="button" onClick={openArtifact}>{status === "loading" ? "Loading" : "Preview"}</button>
      </div>
      <details className={styles.panel}>
        <summary>Provenance</summary>
        <details className={styles.technicalDetails}>
          <summary>Technical details</summary>
          <dl className={styles.metadataGrid}>
            <div><dt>ID</dt><dd>{artifact.artifact_id}</dd></div>
            <div><dt>Type</dt><dd>{artifact.artifact_type}</dd></div>
            <div><dt>Category</dt><dd>{presented.category}</dd></div>
            <div><dt>Stage</dt><dd>{artifact.stage_id ?? "global"}</dd></div>
            <div><dt>Attempt</dt><dd>{attempt ?? presented.attemptLabel ?? "none"}</dd></div>
            <div><dt>Producer</dt><dd>{createdBy?.trim() || "Unavailable"}</dd></div>
            <div><dt>Timestamp</dt><dd>{new Date(artifact.created_at).toISOString()}</dd></div>
            <div><dt>Relative path</dt><dd><code>{presented.rawPath}</code></dd></div>
            <div><dt>Checksum</dt><dd><code>{artifact.checksum}</code></dd></div>
          </dl>
        </details>
      </details>
      {status === "failed" ? <p className={styles.note} role="alert">Artifact preview is unavailable.</p> : null}
      {content ? viewerFor(artifact, content) : null}
    </article>
  );
}

export function ArtifactPreviewPanel(props: ArtifactPreviewPanelProps) {
  const artifact = props.artifact ?? props.presentation?.artifact;
  if (!artifact) {
    return <p className={styles.note}>Artifact preview is unavailable.</p>;
  }
  return <ArtifactPreviewContent {...props} artifact={artifact} />;
}
