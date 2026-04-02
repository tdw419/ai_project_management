/**
 * Lightweight request logger middleware.
 * Logs method, path, status code, and duration in ms to stdout
 * when the response finishes.
 */
function requestLogger(req, res, next) {
  const start = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - start;
    process.stdout.write(`${req.method} ${req.path || '/'} ${res.statusCode} ${duration}ms\n`);
  });

  next();
}

module.exports = requestLogger;
