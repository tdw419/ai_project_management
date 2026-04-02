/**
 * Query functions for truths.db.
 * All functions accept a db handle (or null) and return arrays.
 * They are synchronous (node:sqlite is DatabaseSync) but return values
 * directly for consistency -- callers can use them sync or wrap in promises.
 */

/**
 * Get recent project states, ordered by timestamp desc.
 * @param {import('node:sqlite').DatabaseSync|null} db
 * @param {number} [limit=20]
 * @returns {Array}
 */
function getProjectStates(db, limit = 20) {
  if (!db) return [];
  return db.prepare(
    'SELECT * FROM project_state ORDER BY timestamp DESC LIMIT ?'
  ).all(limit);
}

/**
 * Get history snapshots for a specific project.
 * @param {import('node:sqlite').DatabaseSync|null} db
 * @param {string} projectId
 * @param {number} [limit=10]
 * @returns {Array}
 */
function getProjectHistory(db, projectId, limit = 10) {
  if (!db) return [];
  return db.prepare(
    'SELECT * FROM project_state WHERE project_id = ? ORDER BY timestamp DESC LIMIT ?'
  ).all(projectId, limit);
}

/**
 * Get recent metrics rows.
 * @param {import('node:sqlite').DatabaseSync|null} db
 * @param {number} [limit=50]
 * @returns {Array}
 */
function getRecentMetrics(db, limit = 50) {
  if (!db) return [];
  return db.prepare(
    'SELECT * FROM metrics ORDER BY timestamp DESC LIMIT ?'
  ).all(limit);
}

/**
 * Get recent session_index rows.
 * @param {import('node:sqlite').DatabaseSync|null} db
 * @param {number} [limit=20]
 * @returns {Array}
 */
function getRecentSessions(db, limit = 20) {
  if (!db) return [];
  return db.prepare(
    'SELECT * FROM session_index ORDER BY started_at DESC LIMIT ?'
  ).all(limit);
}

module.exports = {
  getProjectStates,
  getProjectHistory,
  getRecentMetrics,
  getRecentSessions,
};
