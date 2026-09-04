import { useState } from "react";

import { createTask } from "./api";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { Checklist } from "./components/Checklist";
import { LiveTerminal } from "./components/LiveTerminal";
import { LoginForm } from "./components/LoginForm";
import { SplitDiffViewer } from "./components/SplitDiffViewer";
import { TaskForm } from "./components/TaskForm";
import { TaskHistory } from "./components/TaskHistory";
import { useTaskStream } from "./hooks/useTaskStream";
import { AUTH_ENABLED } from "./lib/supabase";
import type { AgentStatus, TaskCreateRequest } from "./types";

const RUNNING_STATUSES: AgentStatus[] = ["pending", "running", "planning", "coding", "testing", "healing"];

function Dashboard() {
  const { user, signOut } = useAuth();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const { state, events } = useTaskStream(taskId);

  const isRunning = state.status !== undefined && RUNNING_STATUSES.includes(state.status);

  async function handleSubmit(req: TaskCreateRequest) {
    setSubmitError(null);
    try {
      const id = await createTask(req);
      setTaskId(id);
      setHistoryRefreshKey((k) => k + 1);
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
        <div className="flex items-center gap-3">
          {taskId && <Checklist events={events} status={state.status} iteration={state.iteration} />}
          {AUTH_ENABLED && user && (
            <div className="flex items-center gap-2 text-xs text-neutral-500">
              <span>{user.email}</span>
              <button onClick={signOut} className="text-sky-400 hover:text-sky-300">
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      <TaskForm onSubmit={handleSubmit} disabled={isRunning} />
      {submitError && <p className="text-sm text-rose-400">{submitError}</p>}

      <TaskHistory onSelect={setTaskId} selectedTaskId={taskId} refreshKey={historyRefreshKey} />

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

function AuthGate() {
  const { session, loading } = useAuth();

  if (!AUTH_ENABLED) return <Dashboard />;
  if (loading) return null;
  if (!session) return <LoginForm />;
  return <Dashboard />;
}

function App() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  );
}

export default App;
