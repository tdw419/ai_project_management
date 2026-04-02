const { describe, it, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { Writable, EventEmitter } = require('stream');

// ---- helpers ----

function captureStream() {
  const chunks = [];
  const stream = new Writable({ write(ch, _enc, cb) { chunks.push(String(ch)); cb(); } });
  stream.getOutput = () => chunks.join('');
  return stream;
}

function mockRes() {
  const r = Object.create(EventEmitter.prototype);
  EventEmitter.call(r);
  r.statusCode = 200;
  r.body = null;
  r.status = function(code) { r.statusCode = code; return r; };
  r.json = function(obj) { r.body = obj; return r; };
  return r;
}

// ---- error-handler tests ----

describe('error-handler', () => {
  let origStderr, stderrCapture;

  beforeEach(() => {
    origStderr = process.stderr;
    stderrCapture = captureStream();
    Object.defineProperty(process, 'stderr', { value: stderrCapture, writable: true, configurable: true });
  });

  afterEach(() => {
    Object.defineProperty(process, 'stderr', { value: origStderr, writable: true, configurable: true });
  });

  it('returns 503 for sqlite errors (code prefix)', () => {
    const errorHandler = require('../src/middleware/error-handler');
    const err = new Error('database is locked');
    err.code = 'SQLITE_BUSY';
    const res = mockRes();
    errorHandler(err, {}, res, () => {});

    assert.equal(res.statusCode, 503);
    assert.deepEqual(res.body, { error: 'service unavailable', detail: 'database is locked' });
  });

  it('returns 503 for errors with sqlite in message', () => {
    const errorHandler = require('../src/middleware/error-handler');
    const err = new Error('sqlite_generic: disk I/O error');
    const res = mockRes();
    errorHandler(err, {}, res, () => {});

    assert.equal(res.statusCode, 503);
    assert.equal(res.body.error, 'service unavailable');
    assert.ok(res.body.detail);
  });

  it('returns 500 for unexpected errors', () => {
    const errorHandler = require('../src/middleware/error-handler');
    const err = new Error('something completely unexpected');
    const res = mockRes();
    errorHandler(err, {}, res, () => {});

    assert.equal(res.statusCode, 500);
    assert.deepEqual(res.body, { error: 'internal server error' });
  });

  it('logs error message to stderr', () => {
    const errorHandler = require('../src/middleware/error-handler');
    const err = new Error('oops test log');
    const res = mockRes();
    errorHandler(err, {}, res, () => {});

    const output = stderrCapture.getOutput();
    assert.ok(output.includes('oops test log'), 'stderr should contain the error message');
  });
});

// ---- request-logger tests ----

describe('request-logger', () => {
  let origStdout, stdoutCapture;

  beforeEach(() => {
    origStdout = process.stdout;
    stdoutCapture = captureStream();
    Object.defineProperty(process, 'stdout', { value: stdoutCapture, writable: true, configurable: true });
  });

  afterEach(() => {
    Object.defineProperty(process, 'stdout', { value: origStdout, writable: true, configurable: true });
  });

  it('logs method, path, status and duration to stdout on finish', (_t, done) => {
    const requestLogger = require('../src/middleware/request-logger');
    const req = { method: 'GET', path: '/api/projects' };
    const res = mockRes();

    requestLogger(req, res, () => {});
    res.statusCode = 200;
    res.emit('finish');

    // Allow any microtask to flush
    setImmediate(() => {
      const output = stdoutCapture.getOutput();
      assert.ok(output.includes('GET'), 'should log method');
      assert.ok(output.includes('/api/projects'), 'should log path');
      assert.ok(output.includes('200'), 'should log status');
      assert.ok(output.includes('ms'), 'should include duration');
      done();
    });
  });

  it('calls next()', () => {
    const requestLogger = require('../src/middleware/request-logger');
    let nextCalled = false;
    requestLogger({}, mockRes(), () => { nextCalled = true; });
    assert.ok(nextCalled, 'next should be called');
  });
});
