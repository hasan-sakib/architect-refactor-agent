# Architecture

## Pipeline

The agent is a [LangGraph](https://github.com/langchain-ai/langgraph) state machine with four nodes, wired as a loop:

```
START -> planner -> coder -> tester --(passed | failed)--> END
                        ^                |
                        |            (else: retry)
                        +----------- self_healer
```

- **Planner** — given the task and (optionally) semantic search results from the codebase's vector index, produces a numbered plan. No code is written here.
- **Coder** — given the plan (and, on a retry, the previous failure), asks the LLM to emit full file contents using a strict `### FILE: path` / `### END FILE` text block per changed file, then writes each file into the sandbox. This text protocol — rather than native LLM tool-calling — was a deliberate choice: tool-calling reliability varies a lot across small local models served through Ollama, and a fixed graph topology with a simple, deterministic parser is more robust than a dynamic tool-selection loop for this use case.
- **Tester** — runs the user-supplied test command inside the sandbox and captures the real exit code, stdout, and stderr.
- **SelfHealer** — only runs after a failed test. Diagnoses the failure from the captured output and produces a revised plan, then loops back to the Coder. Bounded by `max_iterations`; exceeding it ends the run as `failed` rather than looping forever.

Run-scoped dependencies (the live sandbox driver, the vector store) are injected via LangGraph's `context_schema`/`Runtime` mechanism rather than stored in the graph's `state` — state stays plain, JSON-serializable data (useful for the SSE layer and for any future checkpointing), while the driver handle stays out of anything that gets copied or persisted.

## Sandbox isolation

All code execution goes through a `BaseSandboxDriver` interface (`backend/app/drivers/base.py`) — an abstract contract for lifecycle (`build`/`start`/`stop`/`cleanup`), execution (`exec_command`), file I/O (`read_file`/`write_file`), and diagnostics (`get_logs`). The only implementation today is `DockerSandboxDriver`, built on the `docker` Python SDK. No application code is allowed to call the Docker SDK directly — everything goes through the interface, so swapping in a different isolation backend (gVisor, Firecracker, a remote sandbox service) later means writing one new driver class, not touching the agent or API layers.

Each task gets a fresh container from the `refactor-agent-sandbox` image (`backend/Dockerfile.sandbox` — not to be confused with `backend/Dockerfile`, which is the FastAPI app's own image), with the target repo bind-mounted at `/workspace`.

## Model abstraction

All LLM calls go through `backend/app/core/llm.py`'s `get_completion()`, the only module allowed to `import litellm`. Which model runs is controlled entirely by the `LLM_MODEL_NAME` environment variable (`backend/.env`) — switching from a local Ollama model to a hosted one is a one-line config change, not a code change.

## RAG / semantic search

`backend/app/rag/chunker.py` uses `tree-sitter-language-pack`'s structural parsing (not hand-rolled AST traversal) to split source files into semantic units — one chunk per function/method/class, with residual chunks for module-level code (imports, top-level statements) that fall outside any structural item. `backend/app/rag/vector_store.py` wraps a local, persistent ChromaDB collection using its default on-device embedding model — no external embedding API calls. The Planner uses this to ground its plan in relevant existing code before proposing changes.

## API & streaming

FastAPI exposes three routes (`backend/app/api/routes.py`):
- `POST /api/tasks` — starts a run in a background thread, returns a task id immediately.
- `GET /api/tasks/{id}` — full event history and current status (polling/catch-up).
- `GET /api/tasks/{id}/stream` — Server-Sent Events, one event per LangGraph node completion, plus status/log/done/error events.

The executor runs synchronously in a worker thread (dispatched via FastAPI's `BackgroundTasks`); events cross into the asyncio event loop via `loop.call_soon_threadsafe`, fanned out to every connected SSE subscriber for that task. A subscriber connecting after the task has already finished gets a synthetic terminal event immediately rather than hanging.

## Frontend

React + TypeScript, talking to the backend purely through `fetch`/`EventSource` against relative `/api/...` paths — no hardcoded backend origin, so the same build works whether the API is reached via Vite's dev proxy or nginx's reverse proxy in the dockerized setup. `useTaskStream` accumulates SSE events into a single `AgentState` object client-side, mirroring how the backend's own LangGraph state merges. `SplitDiffViewer` uses Monaco's `DiffEditor`, **self-hosted** (not `@monaco-editor/react`'s CDN default) to keep the whole stack local-first.

## Dockerized deployment

`docker-compose.yml` builds both `backend` and `frontend` as containers:
- `backend` uses Docker-outside-of-Docker (the host's `/var/run/docker.sock` is bind-mounted in) so it can still build/start sandbox containers via the *host's* Docker daemon, even though the backend itself now runs inside a container. Bind-mount paths (like an uploaded repo's path) are always resolved by that host daemon against the host filesystem — this is what makes DooD transparent for the paths the app generates on upload.
- The backend container also mirror-mounts a scoped `~/.refactor-agent-uploads` directory at the same path (not the whole home directory — the app is uploads-only, so that's the only path space it ever needs), so the backend's own filesystem checks agree with what the host daemon sees.
- `frontend` is a multi-stage build: compiled by Vite, served by nginx, which also reverse-proxies `/api/*` to the backend — same-origin from the browser's perspective, so no CORS is needed in this path.
- Ollama is deliberately **not** containerized — Docker Desktop on macOS has no Metal/GPU passthrough, so a containerized Ollama would fall back to CPU-only inference. The backend reaches the host's native Ollama via `host.docker.internal`.

## Directory structure

```
architect-refactor-agent/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile              # the FastAPI app's own image
│   ├── Dockerfile.sandbox      # base image for agent-controlled sandboxes
│   ├── requirements.txt
│   ├── scripts/                # manual smoke tests (sandbox, RAG, agent)
│   └── app/
│       ├── api/                # FastAPI routes, SSE, task manager
│       ├── agent/               # LangGraph state machine, nodes, prompts
│       ├── drivers/             # BaseSandboxDriver, DockerSandboxDriver
│       ├── rag/                 # Tree-sitter chunker, ChromaDB manager
│       ├── tools/                # File/exec/search tools used by agent nodes
│       └── core/                 # Config, LiteLLM wrapper, logging
└── frontend/
    ├── Dockerfile / nginx.conf
    └── src/
        ├── components/           # SplitDiffViewer, LiveTerminal, Checklist, TaskForm
        └── hooks/                 # useTaskStream (SSE)
```

## Build phases

The project was built in five phases, each verified end-to-end before moving on:

1. **Setup & Abstraction** — project scaffold, config, `BaseSandboxDriver`/`DockerSandboxDriver`.
2. **Ingestion & RAG** — Tree-sitter chunking, ChromaDB vector store.
3. **LangGraph Logic** — agent tools, the Planner/Coder/Tester/SelfHealer graph.
4. **API & Streaming** — FastAPI routes, the SSE endpoint.
5. **React Dashboard** — Mission Control UI, then a fully-dockerized deployment.
