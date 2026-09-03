import { DiffEditor } from "@monaco-editor/react";
import { useEffect, useState } from "react";

import type { FileChange } from "../types";

const EXTENSION_LANGUAGE: Record<string, string> = {
  py: "python",
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  json: "json",
  md: "markdown",
  yml: "yaml",
  yaml: "yaml",
  html: "html",
  css: "css",
  sh: "shell",
  go: "go",
  rs: "rust",
  java: "java",
};

function guessLanguage(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return EXTENSION_LANGUAGE[ext] ?? "plaintext";
}

interface SplitDiffViewerProps {
  filesChanged: FileChange[];
}

export function SplitDiffViewer({ filesChanged }: SplitDiffViewerProps) {
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  useEffect(() => {
    if (filesChanged.length > 0 && !filesChanged.some((f) => f.path === selectedPath)) {
      setSelectedPath(filesChanged[filesChanged.length - 1].path);
    }
  }, [filesChanged, selectedPath]);

  const selected = filesChanged.find((f) => f.path === selectedPath);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-neutral-800 bg-neutral-950">
      <div className="flex items-center gap-2 overflow-x-auto border-b border-neutral-800 px-3 py-2">
        <span className="shrink-0 text-xs font-medium text-neutral-500">Diff</span>
        {filesChanged.length === 0 && (
          <span className="text-xs text-neutral-600">No file changes yet</span>
        )}
        {filesChanged.map((f) => (
          <button
            key={f.path}
            onClick={() => setSelectedPath(f.path)}
            className={`shrink-0 rounded px-2 py-1 font-mono text-xs transition-colors ${
              f.path === selectedPath
                ? "bg-sky-500/15 text-sky-300"
                : "text-neutral-400 hover:bg-neutral-800"
            }`}
          >
            {f.path}
          </button>
        ))}
      </div>
      <div className="flex-1">
        {selected ? (
          <DiffEditor
            key={selected.path}
            original={selected.before}
            modified={selected.after}
            language={guessLanguage(selected.path)}
            theme="vs-dark"
            options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12 }}
            height="100%"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-neutral-600">
            Select a file to view its diff
          </div>
        )}
      </div>
    </div>
  );
}
