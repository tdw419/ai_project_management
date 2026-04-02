const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { getDb, close } = require('../src/db/truths');

describe('getDb', () => {
  it('returns a db object for a valid sqlite file', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'truths-test-'));
    const dbPath = path.join(tmpDir, 'test.db');
    // Create a minimal sqlite file using node:sqlite itself
    const { DatabaseSync } = require('node:sqlite');
    const setup = new DatabaseSync(dbPath);
    setup.exec('CREATE TABLE t (x INTEGER)');
    setup.close();

    const db = getDb(dbPath);
    assert.ok(db, 'should return a db object');
    assert.ok(typeof db.prepare === 'function', 'should have prepare method');
    close(db);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('returns null when file does not exist', () => {
    const db = getDb('/no/such/path/truths.db');
    assert.equal(db, null);
  });

  it('returns null for a corrupt (non-sqlite) file', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'truths-test-'));
    const dbPath = path.join(tmpDir, 'corrupt.db');
    fs.writeFileSync(dbPath, 'this is not sqlite data');
    const db = getDb(dbPath);
    assert.equal(db, null);
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('uses default path from TRUTHS_DB_PATH env var', () => {
    // Just verify the function exists and reads env -- actual default path
    // tested implicitly. We set a bogus env var and confirm it returns null.
    const orig = process.env.TRUTHS_DB_PATH;
    process.env.TRUTHS_DB_PATH = '/no/such/env/path.db';
    const db = getDb();
    assert.equal(db, null);
    if (orig !== undefined) process.env.TRUTHS_DB_PATH = orig;
    else delete process.env.TRUTHS_DB_PATH;
  });
});

describe('close', () => {
  it('does not throw when passed null', () => {
    assert.doesNotThrow(() => close(null));
  });
});
