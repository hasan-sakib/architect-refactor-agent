export type NodeName = "planner" | "coder" | "tester" | "self_healer";

export type AgentStatus =
  | "pending"
  | "running"
  | "planning"
  | "coding"
  | "testing"
  | "healing"
  | "passed"
  | "failed"
  | "error";

export interface FileChange {
  path: string;
  before: string;
  after: string;
}

/** Mirrors the backend's AgentState — accumulated client-side as SSE events arrive. */
export interface AgentState {
  task?: string;
  test_command?: string;
  plan?: string;
  error_context?: string;
  files_changed?: FileChange[];
  test_output?: string;
  test_exit_code?: number | null;
  iteration?: number;
  max_iterations?: number;
  status?: AgentStatus;
}

export type StreamEvent =
  | { type: "status"; status: AgentStatus }
  | { type: "log"; message: string }
  | { type: "node"; node: NodeName; data: Partial<AgentState> }
  | { type: "done"; status: AgentStatus; final_state: AgentState }
  | { type: "error"; message: string };

export interface TaskCreateRequest {
  repo_path: string;
  task: string;
  test_command: string;
  max_iterations: number;
}
