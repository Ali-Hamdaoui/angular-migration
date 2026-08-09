"use client";

import { useMemo, useState } from "react";
import type { AuthoritativeRunStateDto } from "@/types/generated/api";
import styles from "./ControlTowerLayout.module.css";

type Event = AuthoritativeRunStateDto["workflow_events"][number];
export function WorkflowEventsSection({ events }: { events: Event[] }) {
  const [query, setQuery] = useState(""); const [type, setType] = useState("all"); const [order, setOrder] = useState<"oldest" | "newest">("oldest");
  const types = [...new Set(events.map((event) => event.event_type))].sort();
  const visible = useMemo(() => events.filter((event) => event.event_type.toLowerCase().includes(query.toLowerCase()) && (type === "all" || event.event_type === type)).sort((a, b) => order === "oldest" ? a.sequence - b.sequence : b.sequence - a.sequence), [events, order, query, type]);
  return <section className={styles.eventsPanel} aria-label="Authoritative workflow events"><div className={styles.eventControls}><input aria-label="Search events" placeholder="Search event names" value={query} onChange={(event) => setQuery(event.target.value)} /><select aria-label="Event type filter" value={type} onChange={(event) => setType(event.target.value)}><option value="all">All event types</option>{types.map((item) => <option key={item}>{item}</option>)}</select><button type="button" onClick={() => setOrder(order === "oldest" ? "newest" : "oldest")}>{order === "oldest" ? "Newest first" : "Oldest first"}</button></div>{visible.length ? <ol className={styles.eventsList}>{visible.map((event) => <li key={event.event_id} className={styles.eventRow}><div><strong>#{event.sequence}</strong><code>{event.event_type}</code><time>{event.occurred_at}</time></div><p>{typeof event.payload.message === "string" ? event.payload.message : "Authoritative workflow update"}</p><details><summary>Raw payload</summary><pre>{JSON.stringify(event.payload, null, 2)}</pre></details></li>)}</ol> : <p className={styles.note}>No events match these filters.</p>}</section>;
}
