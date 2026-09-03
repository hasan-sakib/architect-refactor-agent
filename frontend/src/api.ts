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
