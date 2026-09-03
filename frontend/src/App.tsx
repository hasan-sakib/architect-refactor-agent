import { useState } from "react";

import { createTask } from "./api";
import { Checklist } from "./components/Checklist";
import { LiveTerminal } from "./components/LiveTerminal";
import { SplitDiffViewer } from "./components/SplitDiffViewer";
import { TaskForm } from "./components/TaskForm";
import { useTaskStream } from "./hooks/useTaskStream";
import type { AgentStatus, TaskCreateRequest } from "./types";

const RUNNING_STATUSES: AgentStatus[] = ["pending", "running", "planning", "coding", "testing", "healing"];

function App() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { state, events } = useTaskStream(taskId);

  const isRunning = state.status !== undefined && RUNNING_STATUSES.includes(state.status);

  async function handleSubmit(req: TaskCreateRequest) {
    setSubmitError(null);
    try {
      const id = await createTask(req);
      setTaskId(id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="flex h-screen flex-col gap-4 p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-neutral-100">
          Mission Control <span className="text-neutral-600">— Refactor Agent</span>
        </h1>
        {taskId && <Checklist events={events} status={state.status} iteration={state.iteration} />}
      </header>

      <TaskForm onSubmit={handleSubmit} disabled={isRunning} />
      {submitError && <p className="text-sm text-rose-400">{submitError}</p>}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="min-h-0 lg:col-span-2">
          <LiveTerminal events={events} />
        </div>
        <div className="min-h-0 lg:col-span-3">
          <SplitDiffViewer filesChanged={state.files_changed ?? []} />
        </div>
      </div>
    </div>
  );
}

export default App;
