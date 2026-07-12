import styles from "./ControlTowerShell.module.css";

type DiffLine = {
  kind: "file" | "hunk" | "add" | "remove" | "context";
  text: string;
};

function classifyLine(line: string): DiffLine {
  if (line.startsWith("diff --git") || line.startsWith("+++") || line.startsWith("---")) return { kind: "file", text: line };
  if (line.startsWith("@@")) return { kind: "hunk", text: line };
  if (line.startsWith("+") && !line.startsWith("+++")) return { kind: "add", text: line };
  if (line.startsWith("-") && !line.startsWith("---")) return { kind: "remove", text: line };
  return { kind: "context", text: line };
}

export function UnifiedDiffViewer({ content }: { content: string }) {
  const lines = content.split(/\r?\n/).map(classifyLine);

  return (
    <pre className={styles.diffViewer} aria-label="Unified diff viewer" tabIndex={0}>
      {lines.map((line, index) => (
        <span className={styles[`diff_${line.kind}`]} key={`${index}-${line.text.slice(0, 16)}`}>
          <span className={styles.lineNumber}>{index + 1}</span>
          {line.text || " "}
          {"\n"}
        </span>
      ))}
    </pre>
  );
}
