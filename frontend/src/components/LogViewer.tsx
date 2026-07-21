"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCommandLogSummary, getCommandLogs, type CommandLogChunk, type CommandLogSummary } from "@/api/commands";
import { getBackendBaseUrl } from "@/api/client";
import styles from "./ControlTowerShell.module.css";

type LogChunk = {
  sequence: number;
  stream: "stdout" | "stderr" | "system" | string;
  content: string;
  timestamp?: string;
  redacted: boolean;
  truncated: boolean;
};

type SharedViewerProps = {
  search?: string;
  maxLines?: number;
};

export type StaticLogArtifactViewerProps = SharedViewerProps & {
  content: string;
};

export type LiveCommandLogViewerProps = SharedViewerProps & {
  runId: string;
  executionId: string;
  executionStatus?: string;
  stdoutArtifactId?: string | null;
  stderrArtifactId?: string | null;
  apiBase?: string;
};

type ConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "completed"
  | "temporarily_unavailable"
  | "cursor_gap"
  | "not_found"
  | "not_owned"
  | "failed"
  | "paused";

type StreamFilter = "all" | "stdout" | "stderr";

function renderStaticLines(content: string, search: string, maxLines: number) {
  const lines = content.split(/\r?\n/);
  const visibleLines = lines.slice(0, maxLines);
  const normalizedSearch = search.trim().toLowerCase();
  return {
    lines,
    visibleLines,
    hiddenLineCount: Math.max(0, lines.length - visibleLines.length),
    normalizedSearch,
  };
}

export function StaticLogArtifactViewer({ content, search = "", maxLines = 500 }: StaticLogArtifactViewerProps) {
  const { visibleLines, hiddenLineCount, normalizedSearch } = renderStaticLines(content, search, maxLines);
  return (
    <div className={styles.viewerShell} aria-label="Command log viewer">
      <pre className={styles.logViewer} tabIndex={0}>
        {visibleLines.map((line, index) => (
          <span className={normalizedSearch && line.toLowerCase().includes(normalizedSearch) ? styles.logMatch : undefined} key={`${index}-${line.slice(0, 16)}`}>
            <span className={styles.lineNumber}>{index + 1}</span>{line || " "}{"\n"}
          </span>
        ))}
      </pre>
      {hiddenLineCount > 0 ? <p className={styles.note}>{hiddenLineCount} additional log lines available in stored artifact.</p> : null}
    </div>
  );
}

function parseEvent(event: MessageEvent): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(event.data as string);
    return value && typeof value === "object" ? value as Record<string, unknown> : null;
  } catch {
    return null;
  }
}

function errorCode(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function eventSequence(event: MessageEvent, payload: Record<string, unknown>): number | null {
  const sequence = typeof payload.sequence === "number" ? payload.sequence : Number(event.lastEventId);
  return Number.isInteger(sequence) && sequence >= 0 ? sequence : null;
}

function statusLabel(value: ConnectionState): string {
  return value.replaceAll("_", " ");
}

function artifactLink(apiBase: string, artifactId: string | null | undefined): string | null {
  return artifactId ? `${apiBase}/artifacts/${encodeURIComponent(artifactId)}` : null;
}

export function LiveCommandLogViewer({
  runId,
  executionId,
  executionStatus,
  stdoutArtifactId,
  stderrArtifactId,
  search = "",
  maxLines = 500,
  apiBase = `${getBackendBaseUrl()}/api/v1`,
}: LiveCommandLogViewerProps) {
  const [chunks, setChunks] = useState<LogChunk[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [streamMessage, setStreamMessage] = useState<string | null>(null);
  const [streamFilter, setStreamFilter] = useState<StreamFilter>("all");
  const [cursor, setCursor] = useState(0);
  const [summary, setSummary] = useState<CommandLogSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [searchQuery, setSearchQuery] = useState(search);
  const [storedOffset, setStoredOffset] = useState(0);
  const [storedTotal, setStoredTotal] = useState(0);
  const [storedLoading, setStoredLoading] = useState(false);
  const [failureCorrelationId, setFailureCorrelationId] = useState<string | null>(null);
  const [finalStatus, setFinalStatus] = useState(executionStatus ?? "");
  const [followingTail, setFollowingTail] = useState(true);
  const cursorRef = useRef(0);
  const processedRef = useRef<Set<number>>(new Set());
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const retryRef = useRef(0);
  const gapRetryRef = useRef(0);
  const mountedRef = useRef(true);
  const pausedRef = useRef(false);
  const completedRef = useRef(false);
  const preRef = useRef<HTMLPreElement>(null);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const closeSource = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  const updateCursor = useCallback((next: number) => {
    cursorRef.current = next;
    setCursor(next);
  }, []);

  const scheduleReconnect = useCallback((permanent = false) => {
    if (!mountedRef.current || pausedRef.current || permanent || reconnectTimerRef.current !== null) return;
    const delay = Math.min(8000, 500 * 2 ** retryRef.current);
    retryRef.current = Math.min(retryRef.current + 1, 5);
    setConnectionState("reconnecting");
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      connect();
    }, delay);
  // The callback is replaced by the effect below before it is used.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current || pausedRef.current || eventSourceRef.current || completedRef.current) return;
    if (typeof EventSource === "undefined") {
      setConnectionState("temporarily_unavailable");
      setStreamMessage("Live streaming is unavailable in this browser context. Open the finalized artifacts instead.");
      return;
    }
    clearReconnect();
    setConnectionState(retryRef.current === 0 ? "connecting" : "reconnecting");
    const url = `${apiBase}/runs/${encodeURIComponent(runId)}/commands/${encodeURIComponent(executionId)}/logs/stream?cursor=${encodeURIComponent(String(cursorRef.current))}`;
    const source = new EventSource(url);
    eventSourceRef.current = source;

    source.onopen = () => {
      if (!mountedRef.current) return;
      setConnectionState("connected");
      setStreamMessage(null);
      setFailureCorrelationId(null);
      setLoading(false);
      retryRef.current = 0;
    };

    source.addEventListener("command_log", (event) => {
      const payload = parseEvent(event as MessageEvent);
      if (!payload) return;
      const sequence = eventSequence(event as MessageEvent, payload);
      const content = typeof payload.content === "string" ? payload.content : typeof payload.text === "string" ? payload.text : "";
      const stream = typeof payload.stream === "string" ? payload.stream : "system";
      if (sequence === null || processedRef.current.has(sequence) || sequence <= cursorRef.current) return;
      if (sequence > cursorRef.current + 1) {
        gapRetryRef.current += 1;
        setConnectionState("cursor_gap");
        setStreamMessage(`Log replay gap detected before sequence ${sequence}. Replaying from sequence ${cursorRef.current}.`);
        closeSource();
        if (gapRetryRef.current <= 3) scheduleReconnect();
        return;
      }
      gapRetryRef.current = 0;
      processedRef.current.add(sequence);
      updateCursor(sequence);
      setLoading(false);
      setChunks((previous) => {
        const next = [...previous, {
          sequence,
          stream,
          content,
          timestamp: typeof payload.timestamp === "string" ? payload.timestamp : undefined,
          redacted: payload.redacted === true,
          truncated: payload.truncated === true,
        }].sort((left, right) => left.sequence - right.sequence);
        return next.slice(-Math.max(maxLines * 4, 100));
      });
    });

    source.addEventListener("log_checkpoint", (event) => {
      const payload = parseEvent(event as MessageEvent);
      if (!payload) return;
      setSummary((previous) => ({
        ...(previous ?? { execution_id: executionId, run_id: runId, total_chunks: 0, streams: { stdout: 0, stderr: 0, system: 0 }, first_sequence: null, last_sequence: null, finalized: false, finalized_at: null, truncated: { stdout: false, stderr: false }, redaction_applied: false }),
        last_sequence: typeof payload.latest_sequence === "number" ? payload.latest_sequence : previous?.last_sequence ?? null,
        truncated: payload.truncated && typeof payload.truncated === "object" ? payload.truncated as { stdout: boolean; stderr: boolean } : previous?.truncated ?? { stdout: false, stderr: false },
      }));
    });

    source.addEventListener("execution_complete", (event) => {
      const payload = parseEvent(event as MessageEvent);
      if (payload && typeof payload.status === "string") setFinalStatus(payload.status);
      completedRef.current = true;
      setConnectionState("completed");
      clearReconnect();
      closeSource();
    });

    source.addEventListener("stream_error", (event) => {
      const payload = parseEvent(event as MessageEvent);
      const code = errorCode(payload?.code) ?? "LOG_STREAM_FAILED";
      setFailureCorrelationId(typeof payload?.correlation_id === "string" ? payload.correlation_id : null);
      const permanent = code === "EXECUTION_NOT_FOUND" || code === "NOT_FOUND" || code === "NOT_OWNED" || code === "LOG_CURSOR_EXPIRED" || code === "LOG_REPLAY_GAP";
      setConnectionState(code === "EXECUTION_NOT_FOUND" ? "not_found" : code === "NOT_OWNED" ? "not_owned" : code.includes("GAP") ? "cursor_gap" : "failed");
      setStreamMessage(permanent ? `${code}: ${typeof payload?.message === "string" ? payload.message : "Reload the finalized artifacts."}` : "The log stream failed; retrying shortly.");
      closeSource();
      scheduleReconnect(permanent);
    });

    source.onerror = () => {
      if (!mountedRef.current || completedRef.current) return;
      setConnectionState("temporarily_unavailable");
      setStreamMessage("The live connection was interrupted. Reconnecting from the last confirmed sequence.");
      closeSource();
      scheduleReconnect();
    };
  // Reconnects use refs and the current cursor, not the state captured by the initial connection.
  }, [apiBase, clearReconnect, closeSource, executionId, maxLines, runId, scheduleReconnect, updateCursor]);

  useEffect(() => {
    mountedRef.current = true;
    cursorRef.current = 0;
    pausedRef.current = false;
    processedRef.current.clear();
    retryRef.current = 0;
    gapRetryRef.current = 0;
    completedRef.current = false;
    updateCursor(0);
    setChunks([]);
    setLoading(true);
    setIsPaused(false);
    setSearchQuery(search);
    setStoredOffset(0);
    setStoredTotal(0);
    setFailureCorrelationId(null);
    setFinalStatus(executionStatus ?? "");
    void getCommandLogSummary(runId, executionId).then((nextSummary) => { setSummary(nextSummary); setLoading(false); }).catch(() => { setLoading(false); setStreamMessage("The command log summary is temporarily unavailable."); });
    connect();
    return () => {
      mountedRef.current = false;
      clearReconnect();
      closeSource();
    };
  }, [apiBase, clearReconnect, closeSource, connect, executionId, executionStatus, runId, search, updateCursor]);

  const normalizedSearch = searchQuery.trim().toLowerCase();
  const displayedChunks = useMemo(() => chunks.filter((chunk) => streamFilter === "all" || chunk.stream === streamFilter), [chunks, streamFilter]);
  const renderedLines = useMemo(() => displayedChunks.flatMap((chunk) => chunk.content.split(/\r?\n/).map((line) => ({ chunk, line }))).filter(({ line }) => !normalizedSearch || line.toLowerCase().includes(normalizedSearch)), [displayedChunks, normalizedSearch]);
  const visibleLines = renderedLines.slice(-maxLines);
  const hiddenLineCount = Math.max(0, renderedLines.length - visibleLines.length);

  useEffect(() => {
    if (followingTail && preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight;
  }, [followingTail, visibleLines.length]);

  function handleScroll() {
    const element = preRef.current;
    if (!element) return;
    setFollowingTail(element.scrollHeight - element.scrollTop - element.clientHeight < 24);
  }

  function togglePause() {
    if (completedRef.current) return;
    if (pausedRef.current) {
      pausedRef.current = false;
      setIsPaused(false);
      setConnectionState("reconnecting");
      connect();
      return;
    }
    pausedRef.current = true;
    clearReconnect();
    closeSource();
    setIsPaused(true);
    setConnectionState("paused");
  }

  async function loadStoredPage() {
    if (storedLoading) return;
    setStoredLoading(true);
    try {
      const page = await getCommandLogs(runId, executionId, { offset: storedOffset, limit: 100 });
      const storedChunks: LogChunk[] = page.chunks.map((chunk: CommandLogChunk) => ({
        sequence: chunk.sequence,
        stream: chunk.stream,
        content: chunk.text,
        timestamp: chunk.created_at,
        redacted: chunk.redacted,
        truncated: chunk.truncated,
      }));
      setChunks((previous) => {
        const bySequence = new Map(previous.map((chunk) => [chunk.sequence, chunk]));
        storedChunks.forEach((chunk) => bySequence.set(chunk.sequence, chunk));
        return [...bySequence.values()].sort((left, right) => left.sequence - right.sequence).slice(-Math.max(maxLines * 4, 100));
      });
      setStoredOffset((current) => current + page.chunks.length);
      setStoredTotal(page.total);
    } finally {
      setStoredLoading(false);
    }
  }

  return (
    <section className={styles.viewerShell} aria-label="Live command log viewer">
      <div className={styles.logToolbar}>
        <div className={styles.streamFilters}>
          {(["all", "stdout", "stderr"] as const).map((filter) => <button type="button" key={filter} className={streamFilter === filter ? styles.activeFilter : ""} onClick={() => setStreamFilter(filter)}>{filter}</button>)}
        </div>
        <div className={styles.connectionStatus} role="status">{statusLabel(connectionState)} · sequence {cursor}</div>
      </div>
      <div className={styles.logToolbar}>
        <label>Search logs <input aria-label="Search logs" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /></label>
        <button type="button" onClick={togglePause} disabled={connectionState === "completed"}>{isPaused ? "Play live output" : "Pause live output"}</button>
        <button type="button" onClick={() => void loadStoredPage()} disabled={storedLoading || (storedTotal > 0 && storedOffset >= storedTotal)}>{storedLoading ? "Loading stored logs..." : "Load stored logs"}</button>
      </div>
      {loading ? <p role="status">Loading command logs...</p> : null}
      {!loading && chunks.length === 0 ? <p className={styles.note}>No log output is available yet.</p> : null}
      {streamMessage ? <p role="alert">{streamMessage}</p> : null}
      {failureCorrelationId ? <p role="alert">Correlation ID: <code>{failureCorrelationId}</code></p> : null}
      {summary?.truncated.stdout || summary?.truncated.stderr || chunks.some((chunk) => chunk.truncated) ? <p className={styles.note}>Output truncated: {[summary?.truncated.stdout ? "stdout" : "", summary?.truncated.stderr ? "stderr" : "", chunks.some((chunk) => chunk.truncated) ? "stored chunk" : ""].filter(Boolean).join(" and ")}. Open the finalized artifact for the authoritative bounded output.</p> : null}
      <pre ref={preRef} onScroll={handleScroll} className={styles.logViewer} tabIndex={0}>
        {visibleLines.map(({ chunk, line }, index) => <span className={normalizedSearch && line.toLowerCase().includes(normalizedSearch) ? styles.logMatch : undefined} key={`${chunk.sequence}-${index}`}><span className={styles.lineNumber}>{hiddenLineCount + index + 1}</span>{line || " "}{"\n"}</span>)}
      </pre>
      {hiddenLineCount > 0 ? <p className={styles.note}>{hiddenLineCount} older log lines hidden by the live tail limit.</p> : null}
      {!followingTail ? <button type="button" onClick={() => { setFollowingTail(true); if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight; }}>Return to latest output</button> : null}
      {storedTotal > 0 && storedOffset < storedTotal ? <p className={styles.note}>{storedTotal - storedOffset} stored log chunks remain.</p> : null}
      {finalStatus ? <p className={styles.note}>Final command status: {finalStatus.replaceAll("_", " ")}</p> : null}
      <div className={styles.list}>
        {([ ["stdout", stdoutArtifactId], ["stderr", stderrArtifactId] ] as const).map(([name, artifactId]) => { const href = artifactLink(apiBase, artifactId); return href ? <a className={styles.actionLink} key={name} href={href} target="_blank" rel="noreferrer">Open {name} artifact</a> : null; })}
      </div>
    </section>
  );
}

/** Compatibility export for existing static artifact callers. */
export function LogViewer(props: StaticLogArtifactViewerProps) {
  return <StaticLogArtifactViewer {...props} />;
}
