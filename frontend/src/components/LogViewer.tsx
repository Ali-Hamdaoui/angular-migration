import styles from "./ControlTowerShell.module.css";

type LogViewerProps = {
  content: string;
  search?: string;
  maxLines?: number;
};

export function LogViewer({ content, search = "", maxLines = 200 }: LogViewerProps) {
  const allLines = content.split(/\r?\n/);
  const visibleLines = allLines.slice(0, maxLines);
  const normalizedSearch = search.trim().toLowerCase();
  const hiddenLineCount = Math.max(0, allLines.length - visibleLines.length);

  return (
    <div className={styles.viewerShell} aria-label="Command log viewer">
      <pre className={styles.logViewer} tabIndex={0}>
        {visibleLines.map((line, index) => {
          const matched = normalizedSearch.length > 0 && line.toLowerCase().includes(normalizedSearch);
          return (
            <span className={matched ? styles.logMatch : undefined} key={`${index}-${line.slice(0, 16)}`}>
              <span className={styles.lineNumber}>{index + 1}</span>
              {line || " "}
              {"\n"}
            </span>
          );
        })}
      </pre>
      {hiddenLineCount > 0 ? <p className={styles.note}>{hiddenLineCount} additional log lines available in stored artifact.</p> : null}
    </div>
  );
}
