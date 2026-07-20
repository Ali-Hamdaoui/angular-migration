import styles from "./ControlTowerShell.module.css";
import { useMemo } from "react";

interface FileSection {
  header: string;
  lines: string[];
  isMetadata: boolean;
}

function parseDiff(content: string): FileSection[] {
  const sections: FileSection[] = [];
  const rawLines = content.split(/\r?\n/);
  let currentHeader = "";
  let currentLines: string[] = [];
  let currentIsMetadata = false;

  for (const line of rawLines) {
    if (line.startsWith("diff --git")) {
      if (currentHeader) {
        sections.push({ header: currentHeader, lines: currentLines, isMetadata: currentIsMetadata });
      }
      currentHeader = line;
      currentLines = [];
      currentIsMetadata = false;
    } else if (line.startsWith("AMFA-METADATA")) {
      if (currentHeader) {
        sections.push({ header: currentHeader, lines: currentLines, isMetadata: currentIsMetadata });
      }
      currentHeader = line;
      currentLines = [];
      currentIsMetadata = true;
    } else {
      currentLines.push(line);
    }
  }
  if (currentHeader) {
    sections.push({ header: currentHeader, lines: currentLines, isMetadata: currentIsMetadata });
  }
  return sections;
}

function extractFilePath(header: string): string | null {
  const match = header.match(/diff --git a\/(\S+) b\//);
  return match ? match[1] : null;
}

export function UnifiedDiffViewer({
  content,
  selectedFile,
  searchQuery = "",
}: {
  content: string;
  selectedFile?: string | null;
  searchQuery?: string;
}) {
  const fileSections = useMemo(() => parseDiff(content), [content]);

  const filteredSections = useMemo(() => {
    if (!selectedFile) return fileSections;
    return fileSections.filter((section) => {
      const filePath = extractFilePath(section.header);
      return filePath === selectedFile;
    });
  }, [fileSections, selectedFile]);

  const hasSearch = searchQuery.length > 0;

  const renderedLines = useMemo(() => {
    const elements: React.ReactNode[] = [];
    let globalIdx = 0;

    for (const section of filteredSections) {
      if (section.isMetadata) {
        elements.push(
          <span key={globalIdx} className={styles.diff_file}>
            <span className={styles.lineNumber} />
            <span
              style={{
                display: "inline-block",
                padding: "0 8px",
                background: "#e2e8f0",
                borderRadius: "4px",
                fontSize: "11px",
                fontWeight: 600,
                color: "#475569",
              }}
            >
              {section.header}
            </span>
            {"\n"}
          </span>
        );
        globalIdx++;
        continue;
      }

      elements.push(
        <span key={globalIdx} className={styles.diff_file}>
          <span className={styles.lineNumber} />
          {section.header}
          {"\n"}
        </span>
      );
      globalIdx++;

      for (const rawLine of section.lines) {
        const isAdd = rawLine.startsWith("+") && !rawLine.startsWith("+++");
        const isRemove = rawLine.startsWith("-") && !rawLine.startsWith("---");
        const isHunk = rawLine.startsWith("@@");
        const isFileMeta = rawLine.startsWith("+++") || rawLine.startsWith("---");
        const kind = isAdd ? "add" : isRemove ? "remove" : isHunk ? "hunk" : isFileMeta ? "file" : "context";
        const isSearchMatch = hasSearch && rawLine.toLowerCase().includes(searchQuery.toLowerCase());

        elements.push(
          <span
            key={globalIdx}
            className={styles[`diff_${kind}`]}
            style={isSearchMatch ? { backgroundColor: "#fef08a" } : undefined}
          >
            <span className={styles.lineNumber}>{globalIdx}</span>
            {rawLine || " "}
            {"\n"}
          </span>
        );
        globalIdx++;
      }
    }
    return elements;
  }, [filteredSections, hasSearch, searchQuery]);

  if (content.length === 0) {
    return (
      <pre className={styles.diffViewer} aria-label="Unified diff viewer" tabIndex={0}>
        <span className={styles.diff_context}>No diff content available</span>
      </pre>
    );
  }

  if (selectedFile && filteredSections.length === 0) {
    return (
      <pre className={styles.diffViewer} aria-label="Unified diff viewer" tabIndex={0}>
        <span className={styles.diff_context}>File not found in diff output</span>
      </pre>
    );
  }

  return (
    <pre className={styles.diffViewer} aria-label="Unified diff viewer" tabIndex={0}>
      {renderedLines}
    </pre>
  );
}
