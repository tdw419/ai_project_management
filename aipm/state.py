import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

@dataclass
class ProjectState:
    project_id: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    commit_hash: str = ""
    test_passing: int = 0
    test_total: int = 0
    test_output: str = ""
    features_done: List[str] = field(default_factory=list)
    features_next: List[str] = field(default_factory=list)
    health: str = "green"
    consecutive_failures: int = 0

class StateManager:
    """Manages persistent project state in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_state (
                    project_id TEXT,
                    timestamp TEXT,
                    commit_hash TEXT,
                    test_passing INTEGER,
                    test_total INTEGER,
                    test_output TEXT,
                    features_done_json TEXT,
                    features_next_json TEXT,
                    health TEXT,
                    consecutive_failures INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_project_state_id ON project_state(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_project_state_time ON project_state(timestamp)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_cooldown (
                    project TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    last_attempt_time TEXT NOT NULL,
                    last_outcome TEXT NOT NULL,
                    PRIMARY KEY (project, issue_number)
                )
            """)

    def save_state(self, state: ProjectState):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO project_state (
                    project_id, timestamp, commit_hash, test_passing, test_total,
                    test_output, features_done_json, features_next_json, 
                    health, consecutive_failures
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                state.project_id, state.timestamp, state.commit_hash,
                state.test_passing, state.test_total, state.test_output,
                json.dumps(state.features_done), json.dumps(state.features_next),
                state.health, state.consecutive_failures
            ))
            # Keep only the latest 5 rows per project to prevent table bloat
            conn.execute("""
                DELETE FROM project_state WHERE rowid NOT IN (
                    SELECT rowid FROM project_state 
                    WHERE project_id = ? 
                    ORDER BY timestamp DESC LIMIT 5
                ) AND project_id = ?
            """, (state.project_id, state.project_id))

    def get_latest_state(self, project_id: str) -> Optional[ProjectState]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM project_state 
                WHERE project_id = ? 
                ORDER BY timestamp DESC LIMIT 1
            """, (project_id,))
            row = cursor.fetchone()
            if row:
                return ProjectState(
                    project_id=row[0],
                    timestamp=row[1],
                    commit_hash=row[2],
                    test_passing=row[3],
                    test_total=row[4],
                    test_output=row[5],
                    features_done=json.loads(row[6]),
                    features_next=json.loads(row[7]),
                    health=row[8],
                    consecutive_failures=row[9]
                )
        return None
