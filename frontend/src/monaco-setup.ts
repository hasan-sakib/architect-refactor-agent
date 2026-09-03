import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";

// Self-host Monaco instead of @monaco-editor/react's CDN default — this
// project's default stack is local-first (Ollama, ChromaDB, Docker all run
// on-device), so the editor shouldn't be the one piece that needs network.
//
// The worker itself is trickier: monaco-editor's ESM worker entrypoints
// (esm/vs/editor/editor.worker.js) have unresolved relative imports that
// Vite 8/Rolldown's worker plugin currently can't bundle from inside
// node_modules. Monaco's own build already produces a fully self-contained,
// dependency-free worker bundle under min/vs/assets/ (a plain IIFE, no
// import/export) — pull that in as raw text via a glob (the filename has a
// content hash that shifts between monaco-editor versions) and run it as a
// classic Worker from a Blob URL, sidestepping the bundler entirely.
const editorWorkerSources = import.meta.glob("/node_modules/monaco-editor/min/vs/assets/editor.worker-*.js", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;
const editorWorkerSource = Object.values(editorWorkerSources)[0];

self.MonacoEnvironment = {
  getWorker() {
    const blob = new Blob([editorWorkerSource], { type: "application/javascript" });
    return new Worker(URL.createObjectURL(blob));
  },
};

loader.config({ monaco });
