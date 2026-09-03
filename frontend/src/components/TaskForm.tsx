import { useState } from "react";

import type { TaskCreateRequest } from "../types";

interface TaskFormProps {
  onSubmit: (req: TaskCreateRequest) => void;
  disabled: boolean;
}

export function TaskForm({ onSubmit, disabled }: TaskFormProps) {
  const [repoPath, setRepoPath] = useState("");
  const [task, setTask] = useState("");
  const [testCommand, setTestCommand] = useState("pytest -q");
  const [maxIterations, setMaxIterations] = useState(3);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ repo_path: repoPath, task, test_command: testCommand, max_iterations: maxIterations });
      }}
      className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-950 p-4"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          Repository path (host)
          <input
            required
            disabled={disabled}
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/path/to/target/repo"
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-sm text-neutral-100 disabled:opacity-50"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-400">
          Test command (runs inside sandbox)
          <input
            required
            disabled={disabled}
            value={testCommand}
            onChange={(e) => setTestCommand(e.target.value)}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-sm text-neutral-100 disabled:opacity-50"
          />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-xs text-neutral-400">
        Task
        <textarea
          required
          disabled={disabled}
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Describe what the agent should fix or refactor…"
          rows={3}
          className="resize-none rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
        />
      </label>

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-xs text-neutral-400">
          Max self-heal iterations
          <input
            type="number"
            min={0}
            max={10}
            disabled={disabled}
            value={maxIterations}
            onChange={(e) => setMaxIterations(Number(e.target.value))}
            className="w-16 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-100 disabled:opacity-50"
          />
        </label>
        <button
          type="submit"
          disabled={disabled}
          className="rounded bg-sky-500 px-4 py-1.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {disabled ? "Running…" : "Start Task"}
        </button>
      </div>
    </form>
  );
}
