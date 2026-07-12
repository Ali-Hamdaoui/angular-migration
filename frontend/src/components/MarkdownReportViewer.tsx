import styles from "./ControlTowerShell.module.css";

function inlineMarkdown(text: string) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    return <span key={index}>{part}</span>;
  });
}

export function MarkdownReportViewer({ content }: { content: string }) {
  const blocks = content.split(/\r?\n/);

  return (
    <div className={styles.markdownViewer} aria-label="Markdown report viewer">
      {blocks.map((line, index) => {
        if (line.startsWith("# ")) return <h3 key={index}>{inlineMarkdown(line.slice(2))}</h3>;
        if (line.startsWith("## ")) return <h4 key={index}>{inlineMarkdown(line.slice(3))}</h4>;
        if (line.startsWith("- ")) return <p className={styles.markdownBullet} key={index}>{inlineMarkdown(line.slice(2))}</p>;
        if (!line.trim()) return <div className={styles.markdownBreak} key={index} />;
        return <p key={index}>{inlineMarkdown(line)}</p>;
      })}
    </div>
  );
}
