# Dashboard Productization Plan

Refactoring the AIPM Dashboard into a robust, pluggable, and composable product.

## Step 1: Lean Engine
- [x] Create `aipm/core/dashboard_engine.js` (Minimal version of `cms.js`)
- [x] Only load: EventBus, ContentStore, LayoutEngine.
- [x] Deprecate unused modules (AiArchitect, etc.) for the dashboard path.

## Step 2: Pluggable Data Sources
- [x] Define `aipm/core/data_sources/base.js` interface.
- [x] Refactor `AIPMBridgePlugin` into `aipm/core/data_sources/aipm_sqlite.js`.
- [ ] Create `aipm/core/data_sources/json_file.js` for generic usage.

## Step 3: Composable Rendering
- [x] Create `aipm/core/dashboard_renderer.js`.
- [x] Move `renderDashboard` and `renderDetail` out of the core engine.
- [x] Implement a simple template/region system for ANSI blocks.

## Step 4: CLI Consolidation
- [x] Update `bin/aipm-dashboard.js` to support `--source` flags.
- [x] Standardize config loading.

## Step 5: UX Refinement
- [x] Browser: Direct keyboard navigation (no Enter for single digits).
- [ ] Browser: Terminal-native scroll and search.
