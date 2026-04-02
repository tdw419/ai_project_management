# AIPM Frontend Plan

Using the ASCII World CMS to build a real-time dashboard for AIPM.

## Phase 1: Data Integration (AIPM Bridge)
- [x] Create `aipm/plugins/aipm-bridge/index.js` (SQLite + GitHub adapter)
- [ ] Connect bridge to `truths.db` (AIPM project health/status)
- [ ] Integrate GitHub webhooks for real-time queue updates

## Phase 2: Visual Layer (Layout & Dashboards)
- [x] Create `aipm/layouts/aipm-dashboard.json` (Dashboard structure)
- [x] Implement `aipm/plugins/aipm-dashboard/project_list.js` (Sidebar with health dots)
- [x] Implement `aipm/plugins/aipm-dashboard/queue_view.js` (Main area with task cards)

## Phase 3: Real-Time Sync
- [x] Wire bridge events to CMS event bus
- [ ] Implement WebSocket delta updates for browser clients
- [ ] Implement delta updates for SSH terminal clients

## Phase 4: Publishing & Hosting
- [ ] Implement HTTP publisher (Web frontend)
- [x] Implement SSH publisher (Terminal-based dashboard)
- [x] Create `bin/aipm-dashboard.js` entry point

## Success Criteria
- [ ] Dashboard displays live data from AIPM's `truths.db`.
- [ ] Webhook events trigger immediate visual updates in the dashboard.
- [ ] SSH terminal access provides a full-fidelity ASCII view of the status.
