import { useEffect, useState } from "react";

import { getStreamTicket, getTask } from "../api";
import type { AgentState, StreamEvent } from "../types";

export interface TaskStream {
  state: AgentState;
  events: StreamEvent[];
  connected: boolean;
}

const TERMINAL_STATUSES = new Set(["passed", "failed", "error"]);
const MAX_RECONNECT_DELAY_MS = 15000;

function applyEvent(prev: AgentState, event: StreamEvent): AgentState {
  if (event.type === "node") return { ...prev, ...event.data };
  if (event.type === "done") return { ...prev, ...event.final_state };
  if (event.type === "status") return { ...prev, status: event.status };
  return prev;
}

export function useTaskStream(taskId: string | null): TaskStream {
  const [state, setState] = useState<AgentState>({});
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    setState({});
    setEvents([]);
    setConnected(false);

    if (!taskId) return;

    let cancelled = false;
    let source: EventSource | null = null;
    let retryCount = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    const lastSeqRef = { current: 0 };

    function handleEvent(event: StreamEvent) {
      if (event.seq !== undefined) {
        if (event.seq <= lastSeqRef.current) return; // already applied (replay/reconnect overlap)
        lastSeqRef.current = event.seq;
      }
      setEvents((prev) => [...prev, event]);
      setState((prev) => applyEvent(prev, event));
    }

    async function connect() {
      // Hydrate first: taskId may point at an already-finished task from
      // history, in which case we just render it and never open a stream.
      try {
        const snapshot = await getTask(taskId!);
        if (cancelled) return;
        setEvents(snapshot.events);
        let hydrated: AgentState = { status: snapshot.status };
        for (const event of snapshot.events) hydrated = applyEvent(hydrated, event);
        if (snapshot.final_state) hydrated = { ...hydrated, ...snapshot.final_state };
        setState(hydrated);
        lastSeqRef.current = snapshot.events.at(-1)?.seq ?? 0;
        if (TERMINAL_STATUSES.has(snapshot.status)) return;
      } catch {
        if (cancelled) return;
      }

      try {
        const { ticket } = await getStreamTicket(taskId!);
        if (cancelled) return;

        source = new EventSource(
          `/api/tasks/${taskId}/stream?ticket=${encodeURIComponent(ticket)}&after_seq=${lastSeqRef.current}`,
        );
        setConnected(true);
        retryCount = 0;

        source.onmessage = (raw) => handleEvent(JSON.parse(raw.data) as StreamEvent);

        source.addEventListener("end", () => {
          source?.close();
          setConnected(false);
        });

        source.onerror = () => {
          if (cancelled || source?.readyState !== EventSource.CLOSED) return;
          setConnected(false);
          // EventSource retries the same URL on its own, which 401-loops
          // forever once the ticket expires — close it and fetch a fresh
          // ticket ourselves instead, with backoff.
          const delay = Math.min(1000 * 2 ** retryCount, MAX_RECONNECT_DELAY_MS);
          retryCount += 1;
          reconnectTimer = setTimeout(connect, delay);
        };
      } catch {
        if (cancelled) return;
        const delay = Math.min(1000 * 2 ** retryCount, MAX_RECONNECT_DELAY_MS);
        retryCount += 1;
        reconnectTimer = setTimeout(connect, delay);
      }
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      source?.close();
      setConnected(false);
    };
  }, [taskId]);

  return { state, events, connected };
}
