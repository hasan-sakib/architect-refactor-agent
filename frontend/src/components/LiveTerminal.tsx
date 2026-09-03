import { useEffect, useRef } from "react";

import type { StreamEvent } from "../types";

function formatEvent(event: StreamEvent): { text: string; tone: string } {
  switch (event.type) {
    case "status":
      return { text: `[status] ${event.status}`, tone: "text-sky-400" };
    case "log":
      return { text: event.message, tone: "text-neutral-400" };
    case "node": {
      const { node, data } = event;
      if (node === "planner" || node === "self_healer") {
        return { text: `[${node}] ${data.plan ?? ""}`, tone: "text-neutral-200" };
      }
      if (node === "coder") {
        const paths = (data.files_changed ?? []).map((f) => f.path);
        return {
          text: paths.length
            ? `[coder] wrote ${paths.length} file(s): ${paths.join(", ")}`
            : "[coder] produced no parseable file changes",
          tone: paths.length ? "text-neutral-200" : "text-amber-400",
        };
      }
      if (node === "tester") {
        return { text: `[tester]\n${data.test_output ?? ""}`, tone: "text-neutral-300" };
      }
      return { text: `[${node}] ${JSON.stringify(data)}`, tone: "text-neutral-400" };
    }
    case "done":
      return {
        text: `✔ done — status: ${event.status}`,
        tone: event.status === "passed" ? "text-emerald-400" : "text-rose-400",
      };
    case "error":
      return { text: `✖ error: ${event.message}`, tone: "text-rose-400" };
  }
}

interface LiveTerminalProps {
  events: StreamEvent[];
}

export function LiveTerminal({ events }: LiveTerminalProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [events.length]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-neutral-800 bg-black">
      <div className="border-b border-neutral-800 px-3 py-2 text-xs font-medium text-neutral-500">
        Live Terminal
      </div>
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed">
        {events.length === 0 && <p className="text-neutral-600">Waiting for task output…</p>}
        {events.map((event, i) => {
          const { text, tone } = formatEvent(event);
          return (
            <pre key={i} className={`mb-1 whitespace-pre-wrap break-words ${tone}`}>
              {text}
            </pre>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
