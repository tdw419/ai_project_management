const { Router } = require('express');
const { getRecentMetrics } = require('../db/queries');

/**
 * Metrics routes.
 * GET /api/metrics - recent rows from metrics table.
 * Supports ?name= filter query param.
 */
function createMetricsRouter(getDb) {
  const router = Router();

  router.get('/api/metrics', (req, res, next) => {
    try {
      const db = getDb();
      if (!db) {
        return res.status(503).json({ error: 'service unavailable', detail: 'database not available' });
      }
      let rows = getRecentMetrics(db);
      const nameFilter = req.query.name;
      if (nameFilter) {
        rows = rows.filter(r => r.metric_name === nameFilter);
      }
      res.json(rows);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = createMetricsRouter;
