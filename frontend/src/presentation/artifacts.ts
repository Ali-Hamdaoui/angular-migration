import { gateDefinition, isGateId } from "@/presentation/gates";
import type { ArtifactRefDto } from "@/types/generated/api";

export type ArtifactCategory =
  | "gate"
  | "command"
  | "validation"
  | "report"
  | "diff"
  | "snapshot"
  | "diagnostic"
  | "other";

export interface ArtifactPresentation {
  artifact: ArtifactRefDto;
  title: string;
  category: ArtifactCategory;
  stageLabel: string;
  attemptLabel: string | null;
  rawPath: string;
  searchableText: string;
}

const CATEGORY_ORDER: ArtifactCategory[] = [
  "gate",
  "validation",
  "report",
  "diff",
  "command",
  "snapshot",
  "diagnostic",
  "other",
];

const EXPLICIT_TYPE_CATEGORY: Partial<Record<ArtifactRefDto["artifact_type"], ArtifactCategory>> = {
  command_log: "command",
  patch: "diff",
  diff: "diff",
  report: "report",
};

function humanize(raw: string): string {
  const words = raw.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  return words ? `${words[0].toUpperCase()}${words.slice(1)}` : "Untitled artifact";
}

function hasTokenSequence(tokens: string[], left: string, right: string): boolean {
  return tokens.some((token, index) => token === left && tokens[index + 1] === right);
}

function categoryFromStableSegments(artifact: ArtifactRefDto): ArtifactCategory {
  const tokens = `${artifact.stage_id ?? ""}/${artifact.relative_path}`
    .toLowerCase()
    .split(/[\\/._-]+/)
    .filter(Boolean);
  const hasAny = (...candidates: string[]) => candidates.some((candidate) => tokens.includes(candidate));

  if (tokens.some((token) => /^g(?:0[1-9]|1[0-2])$/.test(token)) || hasAny("gate") || hasTokenSequence(tokens, "approval", "package")) return "gate";
  if (hasAny("command", "commands", "stdout", "stderr") || hasTokenSequence(tokens, "execution", "log") || hasTokenSequence(tokens, "npm", "ci")) return "command";
  if (hasAny("validation", "parity", "assurance") || hasTokenSequence(tokens, "test", "result") || hasTokenSequence(tokens, "build", "result")) return "validation";
  if (hasAny("report", "reports", "delivery") || hasTokenSequence(tokens, "migration", "summary")) return "report";
  if (hasAny("diff", "patch") || hasTokenSequence(tokens, "change", "set")) return "diff";
  if (hasAny("snapshot", "inventory", "fingerprint") || hasTokenSequence(tokens, "source", "manifest")) return "snapshot";
  if (hasAny("diagnostic", "diagnostics", "failure", "error") || hasTokenSequence(tokens, "worker", "loss")) return "diagnostic";
  return "other";
}

function stageLabel(artifact: ArtifactRefDto): string {
  const source = `${artifact.stage_id ?? ""}/${artifact.relative_path}`;
  const route = source.match(/(?:^|\D)(18|19|20)\D+(19|20|21)(?:\D|$)/);
  if (route) return `Angular ${route[1]} to ${route[2]}`;
  if (artifact.stage_id) return humanize(artifact.stage_id);

  const normalized = artifact.relative_path.toLowerCase();
  if (normalized.includes("00_job_setup")) return "Setup";
  if (normalized.includes("01_source_snapshot")) return "Source snapshot";
  if (normalized.includes("02_baseline")) return "Baseline";
  if (normalized.includes("03_analysis")) return "Analysis";
  if (normalized.includes("04_feasibility")) return "Feasibility";
  if (normalized.includes("05_plan")) return "Migration plan";
  return "Run";
}

function artifactTitle(artifact: ArtifactRefDto): string {
  const filename = artifact.relative_path.split(/[\\/]/).at(-1) ?? artifact.relative_path;
  const stem = filename.replace(/\.[^.]+$/, "");
  const gateMatch = artifact.relative_path.toUpperCase().match(/(?:^|[/_.-])(G(?:0[1-9]|1[0-2]))(?:[/_.-]|$)/);
  if (gateMatch && isGateId(gateMatch[1]) && /package/i.test(stem)) {
    return `${gateDefinition(gateMatch[1]).label} package`;
  }
  return humanize(stem);
}

function attemptLabel(relativePath: string): string | null {
  const match = relativePath.match(/(?:repair[_-]?)?attempt[_/-]?(\d+)/i);
  return match ? `Attempt ${match[1]}` : null;
}

export function presentArtifact(artifact: ArtifactRefDto): ArtifactPresentation {
  const title = artifactTitle(artifact);
  const category = EXPLICIT_TYPE_CATEGORY[artifact.artifact_type] ?? categoryFromStableSegments(artifact);
  const stage = stageLabel(artifact);
  const attempt = attemptLabel(artifact.relative_path);
  const rawPath = artifact.relative_path;
  const searchableText = [title, rawPath, artifact.checksum, artifact.artifact_type, stage, attempt]
    .filter((value): value is string => Boolean(value))
    .join(" ");

  return {
    artifact,
    title,
    category,
    stageLabel: stage,
    attemptLabel: attempt,
    rawPath,
    searchableText,
  };
}

/**
 * Keep artifact ordering deterministic for the investigation list. Semantic
 * category and journey stage provide stable grouping; recency only orders
 * artifacts inside that group. The artifact id is the final tie breaker so a
 * refresh cannot reshuffle equal timestamps.
 */
export function sortArtifactPresentations(artifacts: ArtifactPresentation[]): ArtifactPresentation[] {
  return [...artifacts].sort((left, right) => {
    const category = CATEGORY_ORDER.indexOf(left.category) - CATEGORY_ORDER.indexOf(right.category);
    if (category !== 0) return category;
    const stage = left.stageLabel.localeCompare(right.stageLabel);
    if (stage !== 0) return stage;
    const created = right.artifact.created_at.localeCompare(left.artifact.created_at);
    if (created !== 0) return created;
    const title = left.title.localeCompare(right.title);
    if (title !== 0) return title;
    return left.artifact.artifact_id.localeCompare(right.artifact.artifact_id);
  });
}
