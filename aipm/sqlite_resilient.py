"""
Resilient SQLite connection helper.

Handles database locks, WAL mode, timeouts, and corrupted state files.
Used by CTRMDatabase and CTRMPromptManager for self-healing (Phase 1.2).
"""

import sqlite3
import time
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


# Default retry config
MAX_RETRIES = 5
RETRY_BACKOFF = 0.2  # seconds, doubles each retry
BUSY_TIMEOUT_MS = 5000


class SQLiteConnectionError(Exception):
    """Raised when all recovery attempts fail."""
    pass


def _enable_wal(conn: sqlite3.Connection) -> None:
    """Enable WAL mode for better concurrent access."""
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass  # Already in WAL or read-only


def _recover_stale_locks(db_path: Path) -> bool:
    """
    Recover from stale lock files (-shm, -wal).

    If the database is locked but no process holds it, the WAL/SHM
    files may be stale. Opening a connection in WAL mode and running
    a checkpoint will clean them up.
    """
    wal_path = Path(f"{db_path}-wal")
    shm_path = Path(f"{db_path}-shm")

    if not (wal_path.exists() or shm_path.exists()):
        return False

    try:
        # Try a checkpoint to flush WAL and release locks
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


def _recover_corrupted(db_path: Path) -> bool:
    """
    Attempt to recover a corrupted database.

    Runs integrity_check. If it fails, copies the DB to .bak
    and attempts to dump/reload via SQL.
    """
    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result and result[0] == "ok":
            return True
    except sqlite3.DatabaseError:
        pass

    # Database is corrupted - attempt recovery
    backup_path = Path(f"{db_path}.bak.{int(time.time())}")

    try:
        # Back up the corrupted file
        shutil.copy2(str(db_path), str(backup_path))

        # Try to dump and reload
        old_conn = sqlite3.connect(str(backup_path))
        dump = list(old_conn.iterdump())
        old_conn.close()

        # Remove corrupted DB and its WAL/SHM
        for suffix in ("", "-wal", "-shm"):
            p = Path(f"{db_path}{suffix}")
            if p.exists():
                p.unlink()

        # Recreate from dump
        new_conn = sqlite3.connect(str(db_path))
        for stmt in dump:
            try:
                new_conn.execute(stmt)
            except sqlite3.Error:
                pass
        new_conn.commit()
        new_conn.close()

        print(f"  [sqlite] Recovered corrupted DB. Backup at {backup_path}")
        return True

    except Exception as e:
        print(f"  [sqlite] Recovery failed: {e}. Backup at {backup_path}")
        return False


@contextmanager
def resilient_connection(
    db_path: Path,
    timeout_ms: int = BUSY_TIMEOUT_MS,
    max_retries: int = MAX_RETRIES,
    row_factory: Optional[type] = None,
):
    """
    Context manager that returns a resilient SQLite connection.

    - Sets busy timeout so concurrent writers wait instead of failing
    - Enables WAL mode for concurrent read/write
    - Retries on OperationalError with exponential backoff
    - Attempts stale lock and corruption recovery

    Usage:
        with resilient_connection(db_path) as conn:
            conn.execute("SELECT ...")
    """
    last_error = None
    backoff = RETRY_BACKOFF

    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(str(db_path), timeout=timeout_ms / 1000)
            conn.execute(f"PRAGMA busy_timeout={timeout_ms}")
            _enable_wal(conn)

            if row_factory:
                conn.row_factory = row_factory

            yield conn
            return

        except sqlite3.OperationalError as e:
            last_error = e
            error_msg = str(e).lower()

            if "locked" in error_msg or "busy" in error_msg:
                if attempt == 1:
                    _recover_stale_locks(db_path)

                time.sleep(backoff)
                backoff *= 2
                continue

            elif "corrupt" in error_msg or "malformed" in error_msg:
                if _recover_corrupted(db_path):
                    continue
                break

            else:
                raise

        except sqlite3.DatabaseError as e:
            last_error = e
            if _recover_corrupted(db_path):
                continue
            break

    raise SQLiteConnectionError(
        f"Failed after {max_retries} attempts: {last_error}"
    )
