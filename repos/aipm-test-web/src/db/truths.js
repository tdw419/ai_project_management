const { DatabaseSync } = require('node:sqlite');
const path = require('path');
const fs = require('fs');

const DEFAULT_DB_PATH = '/home/jericho/zion/projects/aipm/data/truths.db';

/**
 * Open a truths.db sqlite database.
 * @param {string} [dbPath] - Path to the sqlite file. Defaults to
 *   TRUTHS_DB_PATH env var or the standard location.
 * @returns {import('node:sqlite').DatabaseSync|null} The db handle, or null
 *   if the file is missing or corrupt (never throws).
 */
function getDb(dbPath) {
  const resolved = dbPath || process.env.TRUTHS_DB_PATH || DEFAULT_DB_PATH;

  if (!fs.existsSync(resolved)) {
    return null;
  }

  try {
    const db = new DatabaseSync(resolved);
    // Quick sanity check -- if the file isn't actually sqlite this will throw
    db.prepare('SELECT 1').get();
    return db;
  } catch {
    return null;
  }
}

/**
 * Close a database handle. Safe to call with null.
 */
function close(db) {
  if (db) {
    try { db.close(); } catch { /* ignore */ }
  }
}

module.exports = { getDb, close };
