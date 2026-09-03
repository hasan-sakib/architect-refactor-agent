import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";

// Self-host Monaco instead of @monaco-editor/react's CDN default — this
// project's default stack is local-first (Ollama, ChromaDB, Docker all run
// on-device), so the editor shouldn't be the one piece that needs network.
// No custom web worker wiring: this app only uses a read-only DiffEditor, so
// Monaco's main-thread fallback (used automatically when no worker is
// configured) is fine — the language-service workers exist for live
// editing features (autocomplete, validation) that we don't use.
loader.config({ monaco });
