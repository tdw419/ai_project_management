const { Router } = require('express');
const { getProjectStates, getProjectHistory } = require('../db/queries');

/**
 * Project routes.
 * GET /api/projects          - list from project_state
 * GET /api/projects/:id/history - snapshots for a project
 * Both return 503 if db is null.
 */
function createProjectsRouter(getDb) {
  const router = Router();

  router.get('/api/projects', (_req, res, next) => {
    try {
      const db = getDb();
      if (!db) {
        return res.status(503).json({ error: 'service unavailable', detail: 'database not available' });
      }
      const rows = getProjectStates(db);
      res.json(rows);
    } catch (err) {
      next(err);
    }
  });

  router.get('/api/projects/:id/history', (req, res, next) => {
    try {
      const db = getDb();
      if (!db) {
        return res.status(503).json({ error: 'service unavailable', detail: 'database not available' });
      }
      const rows = getProjectHistory(db, req.params.id);
      res.json(rows);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = createProjectsRouter;
