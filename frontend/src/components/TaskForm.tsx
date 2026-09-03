import { useEffect, useRef, useState } from "react";

import { uploadRepository } from "../api";
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
  const [uploadState, setUploadState] = useState<
    { status: "idle" } | { status: "uploading" } | { status: "done"; fileCount: number } | { status: "error"; message: string }
  >({ status: "idle" });

  const fileInputRef = useRef<HTMLInputElement>(null);

  // webkitdirectory has no JSX/TS prop — set it imperatively on the input.
  useEffect(() => {
    fileInputRef.current?.setAttribute("webkitdirectory", "");
  }, []);

  async function handleFolderSelected(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setUploadState({ status: "uploading" });
    try {
      const { repoPath: uploadedPath, fileCount } = await uploadRepository(fileList);
      setRepoPath(uploadedPath);
      setUploadState({ status: "done", fileCount });
    } catch (err) {
      setUploadState({ status: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }

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
          <div className="flex items-center justify-between">
            <span>Repository path (host)</span>
            <button
              type="button"
              disabled={disabled || uploadState.status === "uploading"}
              onClick={() => fileInputRef.current?.click()}
              className="text-xs font-medium text-sky-400 hover:text-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {uploadState.status === "uploading" ? "Uploading…" : "Upload folder instead"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(e) => handleFolderSelected(e.target.files)}
            />
          </div>
          <input
            required
            disabled={disabled}
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/path/to/target/repo"
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-sm text-neutral-100 disabled:opacity-50"
          />
          {uploadState.status === "done" && (
            <span className="text-emerald-400">Uploaded {uploadState.fileCount} file(s)</span>
          )}
          {uploadState.status === "error" && <span className="text-rose-400">{uploadState.message}</span>}
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
