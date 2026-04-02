# PXOS Dashboard Interface Contracts

This document defines the mandatory method signatures and data structures
for the PXOS Dashboard system to prevent API drift during autonomous development.

## DashboardEngine (`aipm/core/dashboard_engine.js`)
- `constructor(config)`: Config keys: `syncPath`, `root`, `dashboard_layout`.
- `initialize()`: (async) Loads 3 ESM modules: EventBus, ContentStore, LayoutEngine.
- `setBridgeData(data)`: Updates internal `bridgeData` cache.
- `bridgeData`: `{ projects: [], logs: [], issues: [], lastSync: null }`.

## DashboardRenderer (`aipm/core/dashboard_renderer.js`)
- `constructor(engine)`: Takes a DashboardEngine instance.
- `render(linkTable)`: Returns ANSI string of the main dashboard view.
  - `linkTable`: `Map<number, {route, type, data}>` for [N] link indices.
- `renderDetail(linkData)`: Returns ANSI string for project/issue detail view.
- Section methods (all return `string[]`):
  - `renderHeader(projects, activeCount, redCount, issues, W)`
  - `renderProjectList(projects, linkTable, W)`
  - `renderQueue(issues, linkTable, projectCount, W)`
  - `renderActivity(logs, W)`
  - `renderFooter(logs, W)`

## Data Structures: `bridgeData`
```json
{
  "projects": [{ "id": "...", "type": "project", "data": { "name": "...", "health": "green|yellow|red", "failures": 0, "tests": { "passing": 0, "total": 0 } } }],
  "logs": [{ "id": "...", "type": "activity", "data": { "project": "...", "issue": 0, "outcome": "success|partial|no_change|trust_violation", "attempt": 1, "files_changed": 0 } }],
  "issues": [{ "id": "...", "type": "task", "data": { "number": 0, "title": "...", "labels": [], "body": "..." } }],
  "lastSync": "ISO-Timestamp"
}
```

## Publisher Interface (`aipm/publishers/ssh_server.js`, `aipm/publishers/http_server.js`)
- `constructor(ctx, options)`: Options MUST include `{ cms, port }`.
  - `cms` is a DashboardEngine instance (must have `renderDashboard`, `renderDetail`, `bridgeData`).
- `initialize()`: (async) Sets up server instances.
- `start()`: (async) Starts listening on the configured port.
- `broadcast()`: Pushes the current dashboard frame to all connected clients.
- `stop()`: Closes all connections and servers.

## Data Source Interface (`aipm/core/data_sources/*.js`)
- `constructor(ctx, options)`: Extends `BaseDataSource`.
- `initialize()`: (async) Opens connections, runs first poll, starts interval.
- `poll()`: (async) Refreshes `this.data` and emits `bridge:sync_complete`.
- `getData()`: Returns the current dataset (standard `bridgeData` schema).
- `stop()`: Clears intervals and closes connections.

## Launcher (`bin/aipm-dashboard.js`)
- CLI args: `--ssh-port PORT`, `--web-port PORT`, `--db PATH`.
- Init order: Engine -> Renderer -> Publishers -> Event listener -> Data source.
  Publishers and event listeners MUST be wired before data source initialization
  so the first sync reaches all clients immediately.
