# dataform-dag

Interactive DAG viewer for a Dataform project's dependency graph — parsed locally from `.sqlx`
files, no cloud connection required. Ships as **one shared core + one shared UI behind two hosts**:
a VS Code extension and a standalone local web app.

> **Status:** early build. `packages/core` (parser + graph + graph sources) and `packages/ui`
> (host-agnostic React Flow canvas + `HostBridge` seam, runnable standalone against a mock bridge)
> are in place; the two hosts (`apps/web`, `apps/extension`) follow. Currently developed inside the
> `airfare-drift` repo, which supplies a real Dataform project as a test fixture; it will move to its
> own repo at MVP.

## Layout

```
dataform-dag/
├── packages/
│   ├── core/   # pure TS: .sqlx parser + graph builder + graph sources (regex | compile)
│   └── ui/     # host-agnostic React Flow canvas + node detail, talks only via HostBridge
└── apps/
    ├── extension/  # (later) VS Code host
    └── web/        # (later) browser host
```

## Try the UI standalone

```bash
npm install
npm run build:core        # ui depends on core's types
npm run dev:ui            # Vite dev server → the DAG canvas against a mock 16-node graph
```

## Parsing strategy: layered graph sources

The core exposes a `GraphSource` seam so the *same* `DataformGraph` can be produced two ways:

- **`ParsedGraphSource`** (default) — a lightweight regex parser over `.sqlx` text. No
  `@dataform/core` dependency, runs in the browser, works on a project that doesn't compile.
- **`CompiledGraphSource`** (opt-in, Node only) — shells out to `dataform compile --json` and maps
  the resolved graph. Higher fidelity (catches inline `config.assertions`, object-form refs, refs
  built in JS blocks) at the cost of requiring the CLI and a compiling project.

Both key nodes by **target name** (`config.name ?? filename`), so their output is interchangeable.

Known regex-tier limitations (by design — use `CompiledGraphSource` when they matter): inline
`config.assertions` are not materialized as separate nodes, and a `ref()` inside a **commented-out**
line of SQL is still counted as a dependency (config-block comments *are* stripped; SQL-body comments
are not). Both are covered by tests so they stay documented boundaries, not surprises.

## Develop

```bash
npm install          # from this directory (workspaces root)
npm run build:core
npm run test:core
```

## Extracting to its own repo

Self-contained by design — nothing references paths outside `dataform-dag/`. To split with history:
`git subtree split -P dataform-dag -b dataform-dag-only`, or just copy the folder and `git init`.
