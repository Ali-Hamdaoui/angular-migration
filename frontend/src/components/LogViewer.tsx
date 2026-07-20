import { useEffect, useRef, useState } from "react";
import styles from "./ControlTowerShell.module.css";

type LogChunk = {
  sequence: number;
  stream: string;
  text: string;
  redacted: boolean;
};

type LogViewerProps = {
  executionId?: string;
  runId?: string;
  content?: string;
  search?: string;
  maxLines?: number;
  apiBase?: string;
};

type StreamFilter = "all" | "stdout" | "stderr";

export function LogViewer({
  content,
  executionId,
  runId,
  search = "",
  maxLines = 500,
  apiBase = "/api/v1",
}: LogViewerProps) {
  const [chunks, setChunks] = useState<LogChunk[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamFilter, setStreamFilter] = useState<StreamFilter>("all");
  const cursorRef = useRef(0);
  const esRef = useRef<EventSource | null>(null);
  const preRef = useRef<HTMLPreElement>(null);

  // Connect to SSE stream
  useEffect(() => {
    if (content !== undefined || !executionId || !runId) return;

    let params = `cursor=${cursorRef.current}`;
    if (streamFilter !== "all") {
      params += `&stream=${streamFilter}`;
    }
    const url = `${apiBase}/runs/${runId}/commands/${executionId}/logs/stream?${params}`;

    const connect = () => {
      if (esRef.current) {
        esRef.current.close();
      }

      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("connected", () => {
        setConnected(true);
        setError(null);
      });

      es.addEventListener("chunk", (event: MessageEvent) => {
        const chunk: LogChunk = JSON.parse(event.data);
        setChunks((prev) => [...prev, chunk]);
      });

      es.addEventListener("cursor", (event: MessageEvent) => {
        const data = JSON.parse(event.data);
        cursorRef.current = data.cursor;
      });

      es.addEventListener("done", () => {
        setConnected(false);
        es.close();
      });

      es.onerror = () => {
        setConnected(false);
        setError("Connection lost — reconnecting…");
        es.close();
        // Reconnect after delay
        setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [content, executionId, runId, apiBase, streamFilter]);

  // Auto-scroll to bottom when new chunks arrive
  useEffect(() => {
    if (preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight;
    }
  }, [chunks]);

  const filteredChunks = chunks.filter((c) => {
    if (streamFilter === "all") return true;
    return c.stream === streamFilter;
  });

  const allLines = (content ?? filteredChunks.map((c) => c.text).join("")).split(/\r?\n/);
  const visibleLines = allLines.slice(0, maxLines);
  const normalizedSearch = search.trim().toLowerCase();
  const hiddenLineCount = Math.max(0, allLines.length - visibleLines.length);

  return (
    <div className={styles.viewerShell} aria-label="Command log viewer">
      <div className={styles.logToolbar}>
        <div className={styles.streamFilters}>
          <button
            className={streamFilter === "all" ? styles.activeFilter : ""}
            onClick={() => setStreamFilter("all")}
          >
            All
          </button>
          <button
            className={streamFilter === "stdout" ? styles.activeFilter : ""}
            onClick={() => setStreamFilter("stdout")}
          >
            stdout
          </button>
          <button
            className={streamFilter === "stderr" ? styles.activeFilter : ""}
            onClick={() => setStreamFilter("stderr")}
          >
            stderr
          </button>
        </div>
        <div className={styles.connectionStatus}>
          {connected ? (
            <span className={styles.connected}>● Live</span>
          ) : error ? (
            <span className={styles.error}>{error}</span>
          ) : (
            <span className={styles.disconnected}>○ Disconnected</span>
          )}
        </div>
      </div>
      <pre ref={preRef} className={styles.logViewer} tabIndex={0}>
        {visibleLines.map((line, index) => {
          const matched =
            normalizedSearch.length > 0 && line.toLowerCase().includes(normalizedSearch);
          return (
            <span
              className={matched ? styles.logMatch : undefined}
              key={`${index}-${line.slice(0, 16)}`}
            >
              <span className={styles.lineNumber}>{index + 1}</span>
              {line || " "}
              {"\n"}
            </span>
          );
        })}
      </pre>
      {hiddenLineCount > 0 ? (
        <p className={styles.note}>
          {hiddenLineCount} additional log lines available in stored artifact.
        </p>
      ) : null}
    </div>
  );
}
