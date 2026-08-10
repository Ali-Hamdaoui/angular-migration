export type PresentationTone = "neutral" | "info" | "success" | "warning" | "danger";

export interface StatusPresentation {
  label: string;
  tone: PresentationTone;
  raw: string;
}

const STATUS_PRESENTATIONS: Record<string, Omit<StatusPresentation, "raw">> = {
  CREATED: { label: "Created", tone: "neutral" },
  COMPLETED: { label: "Complete", tone: "success" },
  SUCCEEDED: { label: "Succeeded", tone: "success" },
  PASSED: { label: "Passed", tone: "success" },
  APPROVED: { label: "Approved", tone: "success" },
  RUNNING: { label: "Running", tone: "info" },
  LOADING: { label: "Loading", tone: "info" },
  CONNECTING: { label: "Connecting", tone: "info" },
  RECOVERING: { label: "Recovering", tone: "warning" },
  RECONNECTING: { label: "Reconnecting", tone: "warning" },
  WAITING: { label: "Waiting", tone: "warning" },
  WAITING_APPROVAL: { label: "Waiting for approval", tone: "warning" },
  WAITING_GATE: { label: "Waiting for gate decision", tone: "warning" },
  WAITING_PROMPT: { label: "Waiting for prompt decision", tone: "warning" },
  BLOCKED: { label: "Blocked", tone: "warning" },
  blocked: { label: "Blocked", tone: "warning" },
  TRANSFORMATION_CONTINUATION_BLOCKED: {
    label: "Transformation continuation blocked",
    tone: "warning",
  },
  FAILED: { label: "Failed", tone: "danger" },
  REJECTED: { label: "Rejected", tone: "danger" },
  CANCELLED: { label: "Cancelled", tone: "danger" },
  TIMED_OUT: { label: "Timed out", tone: "danger" },
};

function sentenceCase(raw: string): string {
  const words = raw.trim().replace(/[_-]+/g, " ").replace(/\s+/g, " ").toLowerCase();
  return words ? `${words[0].toUpperCase()}${words.slice(1)}` : "Unknown status";
}

export function presentStatus(raw: string): StatusPresentation {
  const explicit = Object.prototype.hasOwnProperty.call(STATUS_PRESENTATIONS, raw)
    ? STATUS_PRESENTATIONS[raw]
    : undefined;
  return explicit
    ? { ...explicit, raw }
    : { label: sentenceCase(raw), tone: "neutral", raw };
}
