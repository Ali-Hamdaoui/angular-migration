import type { PropsWithChildren } from "react";
import { ChevronRight, Settings } from "lucide-react";
import styles from "../ControlTowerShell.module.css";

type TechnicalDetailsProps = PropsWithChildren<{
  title: string;
  open?: boolean;
}>;

export function TechnicalDetails({ children, open, title }: TechnicalDetailsProps) {
  return (
    <details className={styles.technicalDetails} open={open}>
      <summary className={styles.technicalDetailsSummary}>
        <Settings aria-hidden="true" size={20} strokeWidth={2} />
        <span>{title}</span>
        <ChevronRight
          aria-hidden="true"
          className={styles.technicalDetailsChevron}
          size={18}
          strokeWidth={2}
        />
      </summary>
      <div className={styles.technicalDetailsContent}>{children}</div>
    </details>
  );
}
