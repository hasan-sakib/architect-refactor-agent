import type { TaskCreateRequest } from "./types";

export async function createTask(req: TaskCreateRequest): Promise<string> {
  const res = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `request failed: ${res.status}`);
  }
  const data = (await res.json()) as { task_id: string };
  return data.task_id;
}

// Mirrors backend/app/rag/indexer.py's EXCLUDED_DIRS — no point uploading
// dependency/build/vcs directories the agent's sandbox will regenerate anyway.
const EXCLUDED_DIR_SEGMENTS = new Set([
  ".git",
  "__pycache__",
  "node_modules",
  ".venv",
  "venv",
  "dist",
  "build",
  ".pytest_cache",
  "data",
]);

/** File objects from an <input webkitdirectory> input carry a non-standard
 * webkitRelativePath, e.g. "myrepo/src/index.js" — not in lib.dom's File type. */
type FileWithPath = File & { webkitRelativePath: string };

export async function uploadRepository(fileList: FileList): Promise<{ repoPath: string; fileCount: number }> {
  const files = Array.from(fileList) as FileWithPath[];
  const included = files.filter(
    (f) => !f.webkitRelativePath.split("/").some((segment) => EXCLUDED_DIR_SEGMENTS.has(segment)),
  );
  if (included.length === 0) {
    throw new Error("no files to upload (folder was empty or fully excluded)");
  }

  const formData = new FormData();
  for (const file of included) {
    formData.append("files", file, file.webkitRelativePath);
  }

  const res = await fetch("/api/uploads", { method: "POST", body: formData });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `upload failed: ${res.status}`);
  }
  const data = (await res.json()) as { repo_path: string; file_count: number };
  return { repoPath: data.repo_path, fileCount: data.file_count };
}
