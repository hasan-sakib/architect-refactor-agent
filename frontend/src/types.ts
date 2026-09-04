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

export type StreamEvent = { seq?: number; ts?: number } & (
  | { type: "status"; status: AgentStatus }
  | { type: "log"; message: string }
  | { type: "node"; node: NodeName; data: Partial<AgentState> }
  | { type: "done"; status: AgentStatus; final_state: AgentState }
  | { type: "error"; message: string }
);

export interface TaskCreateRequest {
  upload_id?: string;
  repo_path?: string;
  task: string;
  test_command: string;
  max_iterations: number;
}

export interface TaskSummary {
  id: string;
  status: AgentStatus;
  task: string;
  created_at: string;
  finished_at: string | null;
}

export interface TaskStatusPayload {
  id: string;
  status: AgentStatus;
  events: StreamEvent[];
  final_state: AgentState | null;
}

export interface ClientConfig {
  allow_host_paths: boolean;
  max_upload_bytes: number;
  max_upload_files: number;
  max_iterations_cap: number;
}
