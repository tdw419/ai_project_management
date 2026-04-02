const { describe, it, beforeEach } = require('node:test');
const assert = require('node:assert/strict');

/**
 * Test for Phase 4: App Bootstrap
 * Verifies index.js exports an Express app with all routes mounted,
 * middleware attached, and does NOT listen on import.
 */

function getRoutes(app) {
  const router = app.router;
  const routes = [];
  if (!router || !router.stack) return routes;
  for (const layer of router.stack) {
    if (layer.route) {
      routes.push(Object.keys(layer.route.methods).join(',').toUpperCase() + ' ' + layer.route.path);
    }
    if (layer.name === 'router' && layer.handle && layer.handle.stack) {
      for (const sub of layer.handle.stack) {
        if (sub.route) {
          routes.push(Object.keys(sub.route.methods).join(',').toUpperCase() + ' ' + sub.route.path);
        }
      }
    }
  }
  return routes;
}

describe('app bootstrap', () => {
  let app;

  beforeEach(() => {
    delete require.cache[require.resolve('../index.js')];
    app = require('../index.js');
  });

  it('exports an Express app (function with .listen)', () => {
    assert.equal(typeof app, 'function');
    assert.equal(typeof app.listen, 'function');
  });

  it('has express.json() body parser mounted', () => {
    const stack = app.router.stack;
    assert.ok(stack.length >= 2, 'should have middleware layers');
    const hasJson = stack.some(l => l.name === 'jsonParser');
    assert.ok(hasJson, 'should have jsonParser layer');
  });

  it('mounts GET /health', () => {
    const routes = getRoutes(app);
    assert.ok(routes.some(r => r.includes('GET') && r.includes('/health')),
      `should mount /health, got: ${routes.join(', ')}`);
  });

  it('mounts /api/projects routes', () => {
    const routes = getRoutes(app);
    assert.ok(routes.some(r => r.includes('/api/projects')),
      `should mount /api/projects, got: ${routes.join(', ')}`);
  });

  it('mounts /api/metrics route', () => {
    const routes = getRoutes(app);
    assert.ok(routes.some(r => r.includes('/api/metrics')),
      `should mount /api/metrics, got: ${routes.join(', ')}`);
  });

  it('mounts /api/sessions route', () => {
    const routes = getRoutes(app);
    assert.ok(routes.some(r => r.includes('/api/sessions')),
      `should mount /api/sessions, got: ${routes.join(', ')}`);
  });

  it('has error-handler as last middleware layer', () => {
    const stack = app.router.stack;
    const lastHandler = stack[stack.length - 1].handle;
    assert.ok(lastHandler, 'should have a final handler');
    // Error handlers have 4 params (err, req, res, next)
    assert.equal(lastHandler.length, 4, 'last handler should be an error handler (4 params)');
  });
});
