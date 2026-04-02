const { Router } = require('express');
const { getRecentSessions } = require('../db/queries');

/**
 * Session routes.
 * GET /api/sessions - recent session_index rows.
 * Supports ?project= filter query param.
 */
function createSessionsRouter(getDb) {
  const router = Router();

  router.get('/api/sessions', (req, res, next) => {
    try {
      const db = getDb();
      if (!db) {
        return res.status(503).json({ error: 'service unavailable', detail: 'database not available' });
      }
      let rows = getRecentSessions(db);
      const projectFilter = req.query.project;
      if (projectFilter) {
        rows = rows.filter(r => r.project === projectFilter);
      }
      res.json(rows);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = createSessionsRouter;
