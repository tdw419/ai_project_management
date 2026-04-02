# CMS Integration Plan

Integrating the 15 CMS modules into a cohesive system with a CLI.

## Phase 1: Integration Glue
- [x] Create `aipm/core/cms.js` (The main CMS class)
- [x] Implement `aipm/core/cms_context.js` (Shared state/config)
- [x] Wire modules: Store, Generator, Router, Renderer, Layout, Theme, Plugin, Architect

## Phase 2: CLI Development
- [x] Create `bin/cms-cli.js`
- [x] Implement commands:
    - `init`: Scaffolds a new CMS project
    - `generate`: Triggers AI content generation
    - `preview`: Starts a local server to view the CMS
    - `publish`: Exports the CMS (various formats)

## Phase 3: Built-in Plugins
- [x] Implement `aipm/plugins/nav_menu.js`
- [ ] Implement `aipm/plugins/content_editor.js`
- [ ] Implement `aipm/plugins/media_gallery.js`

## Phase 4: Publishers
- [x] Implement `aipm/publishers/png_export.js` (RTS format)
- [ ] Implement `aipm/publishers/html_compiler.js`
- [ ] Implement `aipm/publishers/ssh_server.js` (Direct to Geometry OS)

## Success Criteria
- [ ] `cms-cli init` creates a valid structure.
- [ ] `cms-cli generate` populates content via AI.
- [ ] `cms-cli preview` displays a functional UI.
- [ ] `cms-cli publish` produces a bootable `.rts.png`.
