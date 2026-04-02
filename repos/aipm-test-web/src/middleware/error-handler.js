/**
 * Express error handler middleware.
 * - SQLite errors (code starts with SQLITE_ or message contains "sqlite") -> 503
 * - Everything else -> 500
 * Always logs to stderr.
 */
function errorHandler(err, _req, res, _next) {
  const isSqlite =
    (err.code && String(err.code).toUpperCase().startsWith('SQLITE_')) ||
    (err.message && err.message.toLowerCase().includes('sqlite'));

  if (isSqlite) {
    process.stderr.write(`[error] sqlite: ${err.message}\n`);
    res.status(503).json({ error: 'service unavailable', detail: err.message });
  } else {
    process.stderr.write(`[error] ${err.message}\n`);
    res.status(500).json({ error: 'internal server error' });
  }
}

module.exports = errorHandler;
