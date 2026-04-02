const express = require('express');
const { getDb } = require('./src/db/truths');
const createHealthRouter = require('./src/routes/health');
const createProjectsRouter = require('./src/routes/projects');
const createMetricsRouter = require('./src/routes/metrics');
const createSessionsRouter = require('./src/routes/sessions');
const requestLogger = require('./src/middleware/request-logger');
const errorHandler = require('./src/middleware/error-handler');

const app = express();

// Body parsing
app.use(express.json());

// Request logging
app.use(requestLogger);

// Routes -- each factory receives the getDb function for testability
app.use(createHealthRouter(getDb));
app.use(createProjectsRouter(getDb));
app.use(createMetricsRouter(getDb));
app.use(createSessionsRouter(getDb));

// Error handler (must be last, has 4 params)
app.use(errorHandler);

// Only listen when run directly, not when imported for testing
if (require.main === module) {
  const port = process.env.PORT || 3000;
  app.listen(port, () => {
    console.log(`Server listening at http://localhost:${port}`);
  });
}

module.exports = app;
