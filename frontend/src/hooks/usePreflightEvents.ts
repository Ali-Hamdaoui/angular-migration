"use client";

import { useEffect, useRef, useState } from "react";
import { getBackendBaseUrl } from "@/api/client";

export function usePreflightEvents(preflightId: string, onEvent: () => void) {
  const [status, setStatus] = useState<"connecting" | "open" | "reconnecting" | "closed">("connecting");
  const [lastEventId, setLastEventId] = useState<number | null>(null);
  const lastEventRef = useRef<number | null>(null);

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    const connect = () => {
      if (stopped) return;
      const suffix = lastEventRef.current === null ? "" : `?last_event_id=${lastEventRef.current}`;
      source = new EventSource(`${getBackendBaseUrl()}/api/v1/preflights/${encodeURIComponent(preflightId)}/events${suffix}`);
      source.onopen = () => setStatus("open");
      const handle = (event: MessageEvent) => {
        if (event.lastEventId) { lastEventRef.current = Number(event.lastEventId); setLastEventId(lastEventRef.current); }
        onEvent();
      };
      ["PREFLIGHT_CREATED", "G01_APPROVED", "G01_REJECTED", "G01_MODIFICATION_REQUESTED", "APPROVAL_MARKED_STALE"].forEach((name) => source?.addEventListener(name, handle));
      source.onerror = () => {
        source?.close();
        setStatus("reconnecting");
        retry = setTimeout(connect, 1000);
      };
    };
    connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      source?.close();
      setStatus("closed");
    };
  }, [preflightId, onEvent]);

  return { status, lastEventId };
}
