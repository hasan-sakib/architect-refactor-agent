import { useEffect, useState } from "react";

import { listTasks } from "../api";
import type { TaskSummary } from "../types";

interface TaskHistoryProps {
  onSelect: (taskId: string) => void;
  selectedTaskId: string | null;
  refreshKey: number;
}

export function TaskHistory({ onSelect, selectedTaskId, refreshKey }: TaskHistoryProps) {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listTasks()
      .then((result) => {
        if (!cancelled) setTasks(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return (
    <div className="flex max-h-40 flex-col gap-1 overflow-y-auto rounded-lg border border-neutral-800 bg-neutral-950 p-2">
      <span className="px-1 text-xs font-medium text-neutral-500">History</span>
      {error && <p className="px-1 text-xs text-rose-400">{error}</p>}
      {tasks.length === 0 && !error && <p className="px-1 text-xs text-neutral-600">No tasks yet</p>}
      {tasks.map((t) => (
        <button
          key={t.id}
          onClick={() => onSelect(t.id)}
          className={`flex items-center justify-between rounded px-2 py-1 text-left text-xs transition-colors ${
            t.id === selectedTaskId ? "bg-sky-500/15 text-sky-300" : "text-neutral-400 hover:bg-neutral-800"
          }`}
        >
          <span className="truncate">{t.task}</span>
          <span className="ml-2 shrink-0 text-neutral-600">{t.status}</span>
        </button>
      ))}
    </div>
  );
}
