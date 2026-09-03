import type { AgentStatus, NodeName, StreamEvent } from "../types";

const STAGES: { key: NodeName; label: string }[] = [
  { key: "planner", label: "Planner" },
  { key: "coder", label: "Coder" },
  { key: "tester", label: "Tester" },
  { key: "self_healer", label: "SelfHealer" },
];

const TERMINAL_STATUSES: AgentStatus[] = ["passed", "failed", "error"];

const STATUS_STYLES: Record<string, string> = {
  passed: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  failed: "bg-rose-500/15 text-rose-400 border-rose-500/30",
  error: "bg-rose-500/15 text-rose-400 border-rose-500/30",
  default: "bg-sky-500/15 text-sky-400 border-sky-500/30",
};

interface ChecklistProps {
  events: StreamEvent[];
  status?: AgentStatus;
  iteration?: number;
}

export function Checklist({ events, status, iteration }: ChecklistProps) {
  const nodeEvents = events.filter(
    (e): e is Extract<StreamEvent, { type: "node" }> => e.type === "node",
  );
  const seen = new Set(nodeEvents.map((e) => e.node));
  const lastNode = nodeEvents.at(-1)?.node;
  const isTerminal = status !== undefined && TERMINAL_STATUSES.includes(status);

  const visibleStages = STAGES.filter((s) => s.key !== "self_healer" || seen.has("self_healer"));

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        {visibleStages.map((stage, i) => {
          const active = !isTerminal && lastNode === stage.key;
          const done = seen.has(stage.key) && !active;
          return (
            <div key={stage.key} className="flex items-center gap-2">
              <span
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  active
                    ? "border-sky-500/50 bg-sky-500/15 text-sky-300"
                    : done
                      ? "border-neutral-700 bg-neutral-800 text-neutral-400"
                      : "border-neutral-800 bg-neutral-900 text-neutral-600"
                }`}
              >
                {active ? "● " : done ? "✓ " : ""}
                {stage.label}
              </span>
              {i < visibleStages.length - 1 && <span className="text-neutral-700">→</span>}
            </div>
          );
        })}
      </div>

      {!!iteration && (
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-400">
          retry {iteration}
        </span>
      )}

      {status && (
        <span
          className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
            STATUS_STYLES[status] ?? STATUS_STYLES.default
          }`}
        >
          {status}
        </span>
      )}
    </div>
  );
}
