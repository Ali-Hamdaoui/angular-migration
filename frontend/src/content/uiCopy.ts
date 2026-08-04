/**
 * Canonical user-facing UI copy for the Angular Migration Control Tower.
 *
 * This module centralizes product branding, navigation labels, section
 * headings, pipeline display labels, and gate display names so the sidebar,
 * dashboard headings, metadata, and landing screen never use conflicting
 * names.
 *
 * Business logic, event mappings, API code, and state machines must NOT live
 * here. This is presentation copy only.
 */

export const PRODUCT_NAME = "Angular Migration Control Tower";
export const PRODUCT_DESCRIPTION =
  "Prepare, review, and monitor controlled Angular migration runs.";

export const LANDING_TAGLINE =
  "Prepare, review, and monitor a controlled Angular migration.";
export const LANDING_ACTION = "Prepare migration";

export const NAV_GROUPS = [
  {
    label: "Migration",
    items: [
      { key: "overview", label: "Overview" },
      { key: "pipeline", label: "Migration preparation" },
      { key: "transformation", label: "Migration execution" },
    ],
  },
  {
    label: "Assessment and planning",
    items: [
      { key: "analysis", label: "Analysis review" },
      { key: "feasibility", label: "Compatibility review" },
      { key: "planning", label: "Migration plan" },
      { key: "discovery", label: "Project discovery" },
      { key: "parity", label: "Baseline comparison" },
    ],
  },
  {
    label: "Evidence and monitoring",
    items: [
      { key: "evidence", label: "Evidence files" },
      { key: "llm", label: "AI activity" },
      { key: "events", label: "Event history" },
    ],
  },
] as const;

export const SECTION_HEADINGS: Record<string, { title: string; description: string }> = {
  overview: {
    title: "Overview",
    description: "The current backend-owned run projection.",
  },
  pipeline: {
    title: "Migration preparation",
    description: "A compact stage view of the authoritative workflow.",
  },
  transformation: {
    title: "Migration execution",
    description: "The complete backend-owned migration execution workflow, evidence, and human actions.",
  },
  analysis: {
    title: "Analysis review",
    description: "Reviewer output and the next human decision.",
  },
  feasibility: {
    title: "Compatibility review",
    description: "Compatibility evidence and feasibility approval.",
  },
  planning: {
    title: "Migration plan",
    description: "Migration plan, review, and approval.",
  },
  discovery: {
    title: "Project discovery",
    description: "Findings captured from the authoritative discovery phase.",
  },
  parity: {
    title: "Baseline comparison",
    description: "Baseline and parity evidence.",
  },
  evidence: {
    title: "Evidence files",
    description: "Immutable evidence registered by the backend.",
  },
  llm: {
    title: "AI activity",
    description: "Provider activity and usage projected from the run.",
  },
  events: {
    title: "Event history",
    description: "Searchable ordered history from the authoritative stream.",
  },
};

export const GATE_NAMES: Record<string, string> = {
  G01: "Migration authorization",
  G02: "Source approval",
  G03: "Baseline approval",
  G04: "Analysis approval",
  G05: "Compatibility approval",
  G06: "Plan approval",
};

export const PIPELINE_LABELS: Record<string, string> = {
  "source-intake": "Read source application",
  "source-snapshot": "Create source snapshot",
  "source-approval": "Source approval",
  "runtime-validation": "Check compatible runtime",
  "baseline-preparation": "Prepare baseline workspace",
  "dependency-installation": "Install dependencies",
  "baseline-build": "Build baseline",
  "baseline-tests": "Run baseline tests",
  "baseline-lint": "Run baseline lint",
  "baseline-qualification": "Review baseline results",
  "baseline-approval": "Baseline approval",
};