"use client";

import { useMemo, useState } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import { presentStatus } from "@/presentation/status";
import styles from "./ControlTowerLayout.module.css";

type Event = AuthoritativeRunStateDto["workflow_events"][number];

function EventTechnicalDetails({ event }: { event: Event }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={(entry) => setOpen(entry.currentTarget.open)}><summary>Technical details</summary><dl className={styles.technicalGrid}><div><dt>Raw event type</dt><dd><code>{event.event_type}</code></dd></div><div><dt>Sequence</dt><dd>Sequence {event.sequence}</dd></div><div><dt>Event ID</dt><dd><code>{event.event_id}</code></dd></div><div><dt>Stage</dt><dd>{event.stage_id ?? "Not available"}</dd></div></dl>{open ? <pre>{JSON.stringify(event.payload, null, 2)}</pre> : null}</details>;
}

export function WorkflowEventsSection({ events }: { events: Event[] }) {
  const [query, setQuery] = useState(""); const [type, setType] = useState("all"); const [order, setOrder] = useState<"oldest" | "newest">("oldest");
  const types = [...new Set(events.map((event) => event.event_type))].sort();
  const visible = useMemo(() => events.filter((event) => {
    const normalizedQuery = query.toLowerCase();
    const presentation = presentStatus(event.event_type).label.toLowerCase();
    return (event.event_type.toLowerCase().includes(normalizedQuery) || presentation.includes(normalizedQuery))
      && (type === "all" || event.event_type === type);
  }).sort((a, b) => order === "oldest" ? a.sequence - b.sequence : b.sequence - a.sequence), [events, order, query, type]);
  return <section className={styles.eventsPanel} aria-label="Authoritative workflow events"><div className={styles.eventControls}><input aria-label="Search events" placeholder="Search event names" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="Event type filter" value={type} onChange={(event) => setType(event.target.value)}><option value="all">All event types</option>{types.map((item) => <option key={item} value={item}>{presentStatus(item).label}</option>)}</select><button type="button" onClick={() => setOrder(order === "oldest" ? "newest" : "oldest")}>{order === "oldest" ? "Newest first" : "Oldest first"}</button></div>{visible.length ? <ol className={styles.eventsList}>{visible.map((event) => <li key={event.event_id} className={styles.eventRow}><div><strong>#{event.sequence}</strong><span>{presentStatus(event.event_type).label}</span><time dateTime={event.occurred_at}>{event.occurred_at}</time></div><p>{typeof event.payload.message === "string" ? event.payload.message : "Authoritative workflow update"}</p><EventTechnicalDetails event={event} /></li>)}</ol> : <p className={styles.note}>No events match these filters.</p>}</section>;
}
