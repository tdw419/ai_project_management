const { Router } = require('express');

/**
 * Health check route.
 * Tests db connectivity with SELECT 1.
 * Returns { status, db, uptime }.
 */
function createHealthRouter(getDb) {
  const router = Router();

  router.get('/health', (_req, res) => {
    const db = getDb();
    let dbOk = false;

    if (db) {
      try {
        db.prepare('SELECT 1').get();
        dbOk = true;
      } catch {
        dbOk = false;
      }
    }

    res.json({ status: 'ok', db: dbOk, uptime: process.uptime() });
  });

  return router;
}

module.exports = createHealthRouter;
