import {
  Circle,
  CircleCheck,
  CircleX,
  Info,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { gateDefinition, isGateId } from "@/presentation/gates";
import {
  presentStatus,
  type PresentationTone,
  type StatusPresentation,
} from "@/presentation/status";
import styles from "./ControlTowerShell.module.css";

type StatusPillProps =
  | { status: string | StatusPresentation; value?: never }
  | { status?: never; value: string };

const TONE_ICONS: Record<PresentationTone, LucideIcon> = {
  neutral: Circle,
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  danger: CircleX,
};

function resolvePresentation(
  status: string | StatusPresentation,
): StatusPresentation {
  if (typeof status !== "string") return status;

  const gateCreated = /^(G\d{2})_CREATED$/.exec(status);
  const gateId = gateCreated?.[1];
  if (isGateId(gateId)) {
    return {
      label: `${gateDefinition(gateId).label} required`,
      tone: "warning",
      raw: status,
    };
  }

  return presentStatus(status);
}

export function StatusPill(props: StatusPillProps) {
  const presentation = resolvePresentation(props.status ?? props.value);
  const ToneIcon = TONE_ICONS[presentation.tone];

  return (
    <span className={styles.status} data-tone={presentation.tone}>
      <ToneIcon aria-hidden="true" size={16} strokeWidth={2} />
      {presentation.label}
    </span>
  );
}
