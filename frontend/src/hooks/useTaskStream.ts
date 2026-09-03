import { useEffect, useRef, useState } from "react";

import type { AgentState, StreamEvent } from "../types";

export interface TaskStream {
  state: AgentState;
  events: StreamEvent[];
  connected: boolean;
}

export function useTaskStream(taskId: string | null): TaskStream {
  const [state, setState] = useState<AgentState>({});
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setState({});
    setEvents([]);
    setConnected(false);

    if (!taskId) return;

    const source = new EventSource(`/api/tasks/${taskId}/stream`);
    sourceRef.current = source;
    setConnected(true);

    source.onmessage = (raw) => {
      const event = JSON.parse(raw.data) as StreamEvent;
      setEvents((prev) => [...prev, event]);
      if (event.type === "node") {
        setState((prev) => ({ ...prev, ...event.data }));
      } else if (event.type === "done") {
        setState((prev) => ({ ...prev, ...event.final_state }));
      } else if (event.type === "status") {
        setState((prev) => ({ ...prev, status: event.status }));
      }
    };

    source.addEventListener("end", () => {
      source.close();
      setConnected(false);
    });

    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        setConnected(false);
      }
    };

    return () => {
      source.close();
      sourceRef.current = null;
      setConnected(false);
    };
  }, [taskId]);

  return { state, events, connected };
}
