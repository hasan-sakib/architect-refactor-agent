import { AUTH_ENABLED, supabase } from "./lib/supabase";
import type { ClientConfig, TaskCreateRequest, TaskStatusPayload, TaskSummary } from "./types";

async function authHeaders(): Promise<HeadersInit> {
  if (!AUTH_ENABLED || !supabase) return {};
  // Fetch fresh every call, never cache — supabase-js auto-refreshes the
  // ~1h access token in the background, and a cached copy produces
  // mysterious 401s exactly one hour into a session.
  const { data } = await supabase.auth.getSession();
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {};
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = { ...(await authHeaders()), ...(init.headers ?? {}) };
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401 && supabase) {
    await supabase.auth.signOut();
  }
  return res;
}

async function throwOnError(res: Response, fallbackPrefix: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(body.detail ?? `${fallbackPrefix}: ${res.status}`);
}

export async function getClientConfig(): Promise<ClientConfig> {
  const res = await fetch("/api/config");
  if (!res.ok) return throwOnError(res, "failed to load config");
  return res.json();
}

export async function createTask(req: TaskCreateRequest): Promise<string> {
  const res = await apiFetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) return throwOnError(res, "request failed");
  const data = (await res.json()) as { task_id: string };
  return data.task_id;
}

export async function listTasks(): Promise<TaskSummary[]> {
  const res = await apiFetch("/api/tasks");
  if (!res.ok) return throwOnError(res, "failed to list tasks");
  return res.json();
}

export async function getTask(taskId: string): Promise<TaskStatusPayload> {
  const res = await apiFetch(`/api/tasks/${taskId}`);
  if (!res.ok) return throwOnError(res, "failed to load task");
  return res.json();
}

export async function getStreamTicket(taskId: string): Promise<{ ticket: string; expiresIn: number }> {
  const res = await apiFetch(`/api/tasks/${taskId}/stream-ticket`, { method: "POST" });
  if (!res.ok) return throwOnError(res, "failed to get stream ticket");
  const data = (await res.json()) as { ticket: string; expires_in: number };
  return { ticket: data.ticket, expiresIn: data.expires_in };
}

// Mirrors backend/app/rag/indexer.py's EXCLUDED_DIRS, extended with common
// dependency/build/cache dirs from other ecosystems — no point uploading
// anything the agent's sandbox would regenerate anyway, and it keeps real
// uploads well under the size limit below.
const EXCLUDED_DIR_SEGMENTS = new Set([
  ".git",
  "__pycache__",
  "node_modules",
  ".venv",
  "venv",
  "dist",
  "build",
  "out",
  ".next",
  ".nuxt",
  "target",
  "vendor",
  ".cache",
  "coverage",
  ".gradle",
  "Pods",
  "data",
]);

// Mirrors backend/app/core/config.py's MAX_UPLOAD_BYTES/MAX_UPLOAD_FILES —
// sized for a public multi-tenant deployment, not solo personal use. Must
// stay comfortably under nginx's `client_max_body_size` (frontend/nginx.conf)
// to leave room for multipart overhead, and to fail fast client-side with a
// clear message instead of a generic 413 after uploading everything.
// TODO(Phase 3): fetch these from GET /api/config instead of hardcoding a
// second copy that can drift.
const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
// Starlette's multipart parser hard-caps at 1000 files per request server-side
// regardless of our own setting — kept in sync here too.
const MAX_UPLOAD_FILES = 1000;

/** File objects from an <input webkitdirectory> input carry a non-standard
 * webkitRelativePath, e.g. "myrepo/src/index.js" — not in lib.dom's File type. */
type FileWithPath = File & { webkitRelativePath: string };

function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
}

export async function uploadRepository(
  fileList: FileList,
): Promise<{ uploadId: string; repoPath: string; fileCount: number }> {
  const files = Array.from(fileList) as FileWithPath[];
  const included = files.filter(
    (f) => !f.webkitRelativePath.split("/").some((segment) => EXCLUDED_DIR_SEGMENTS.has(segment)),
  );
  if (included.length === 0) {
    throw new Error("no files to upload (folder was empty or fully excluded)");
  }

  if (included.length > MAX_UPLOAD_FILES) {
    throw new Error(
      `folder has ${included.length} files after excluding node_modules/.git/build dirs — ` +
        `that's over the ${MAX_UPLOAD_FILES}-file limit. Pick a smaller folder.`,
    );
  }

  const totalBytes = included.reduce((sum, f) => sum + f.size, 0);
  if (totalBytes > MAX_UPLOAD_BYTES) {
    throw new Error(
      `folder is ${formatBytes(totalBytes)} after excluding node_modules/.git/build dirs — ` +
        `that's over the ${formatBytes(MAX_UPLOAD_BYTES)} upload limit. Pick a smaller folder.`,
    );
  }

  const formData = new FormData();
  for (const file of included) {
    formData.append("files", file, file.webkitRelativePath);
  }

  const res = await apiFetch("/api/uploads", { method: "POST", body: formData });
  if (!res.ok) {
    if (res.status === 413) {
      throw new Error("upload rejected as too large by the server — pick a smaller folder.");
    }
    return throwOnError(res, "upload failed");
  }
  const data = (await res.json()) as { upload_id: string; repo_path: string; file_count: number };
  return { uploadId: data.upload_id, repoPath: data.repo_path, fileCount: data.file_count };
}
