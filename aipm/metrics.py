"""
Metrics store -- time-series data for AIPM watchdog.

Stores numeric metrics with timestamps so the watchdog can track trends
over time (rate limit usage, success rates, failure streaks, etc.).
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List, Tuple


class MetricsStore:
    """Simple time-series metrics stored in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    tags_json TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_name_time
                ON metrics(metric_name, timestamp)
            """)

    def put(self, name: str, value: float, tags: dict = None):
        """Record a metric value right now."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO metrics (timestamp, metric_name, metric_value, tags_json) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), name, value, json.dumps(tags or {})),
            )
            # Prune: keep only last 1440 rows per metric (24h at 1/min)
            conn.execute("""
                DELETE FROM metrics WHERE id NOT IN (
                    SELECT id FROM metrics m2
                    WHERE m2.metric_name = metrics.metric_name
                    ORDER BY timestamp DESC LIMIT 1440
                ) AND metric_name = ?
            """, (name,))

    def get_latest(self, name: str) -> Optional[float]:
        """Get the most recent value for a metric."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT metric_value FROM metrics WHERE metric_name = ? ORDER BY timestamp DESC LIMIT 1",
                (name,),
            ).fetchone()
            return row[0] if row else None

    def get_series(self, name: str, hours: float = 1.0) -> List[Tuple[str, float]]:
        """Get recent values for a metric within the last N hours."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT timestamp, metric_value FROM metrics WHERE metric_name = ? AND timestamp >= ? ORDER BY timestamp",
                (name, since),
            ).fetchall()
            return [(r[0], r[1]) for r in rows]

    def get_trend(self, name: str, hours: float = 1.0) -> str:
        """Get a simple trend: 'rising', 'falling', 'stable', 'unknown'."""
        series = self.get_series(name, hours)
        if len(series) < 2:
            return "unknown"
        mid = len(series) // 2
        first_avg = sum(v for _, v in series[:mid]) / max(mid, 1)
        second_avg = sum(v for _, v in series[mid:]) / max(len(series) - mid, 1)
        if first_avg == 0:
            return "unknown"
        if second_avg > first_avg * 1.1:
            return "rising"
        elif second_avg < first_avg * 0.9:
            return "falling"
        return "stable"
