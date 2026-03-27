"""
Prompt Queue - Manages the queue of prompts

SQLite-backed queue for persistent prompt storage.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from aipm.core.engine import Prompt, PromptStatus, PromptCategory
from aipm.config import QUEUE_DB


class PromptQueue:
    """
    SQLite-backed prompt queue.
    
    Provides:
    - Persistent storage
    - Status tracking
    - Statistics
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or QUEUE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority INTEGER DEFAULT 5,
                    confidence REAL DEFAULT 0.5,
                    impact REAL DEFAULT 0.5,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT,
                    result_quality TEXT,
                    metadata TEXT,
                    template_id TEXT,
                    parent_id TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON prompts(status)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_priority ON prompts(priority)
            """)
    
    def add(self, prompt: Prompt) -> None:
        """Add a prompt to the queue"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO prompts (
                    id, text, category, priority, confidence, impact,
                    status, created_at, updated_at, result, result_quality,
                    metadata, template_id, parent_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prompt.id,
                prompt.text,
                prompt.category.value,
                prompt.priority,
                prompt.confidence,
                prompt.impact,
                prompt.status.value,
                prompt.created_at.isoformat(),
                prompt.updated_at.isoformat(),
                prompt.result,
                prompt.result_quality,
                json.dumps(prompt.metadata),
                prompt.template_id,
                prompt.parent_id,
            ))
    
    def get(self, prompt_id: str) -> Optional[Prompt]:
        """Get a prompt by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM prompts WHERE id = ?", (prompt_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_prompt(row)
        return None
    
    def update(self, prompt: Prompt) -> None:
        """Update a prompt"""
        prompt.updated_at = datetime.now()
        self.add(prompt)  # INSERT OR REPLACE
    
    def delete(self, prompt_id: str) -> None:
        """Delete a prompt"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    
    def get_pending(self, limit: int = 100) -> List[Prompt]:
        """Get all pending prompts"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM prompts 
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
            """, (limit,))
            return [self._row_to_prompt(row) for row in cursor.fetchall()]
    
    def get_by_status(self, status: PromptStatus, limit: int = 100) -> List[Prompt]:
        """Get prompts by status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM prompts 
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (status.value, limit))
            return [self._row_to_prompt(row) for row in cursor.fetchall()]
    
    def get_recent(self, limit: int = 20) -> List[Prompt]:
        """Get recently updated prompts"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM prompts 
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))
            return [self._row_to_prompt(row) for row in cursor.fetchall()]
    
    def get_children(self, parent_id: str) -> List[Prompt]:
        """Get follow-up prompts for a parent"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM prompts 
                WHERE parent_id = ?
                ORDER BY created_at ASC
            """, (parent_id,))
            return [self._row_to_prompt(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}
            
            # Total counts by status
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM prompts
                GROUP BY status
            """)
            stats["by_status"] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Total count
            cursor = conn.execute("SELECT COUNT(*) FROM prompts")
            stats["total"] = cursor.fetchone()[0]
            
            # Pending count
            stats["pending"] = stats["by_status"].get("pending", 0)
            
            # Completed today
            today = datetime.now().date().isoformat()
            cursor = conn.execute("""
                SELECT COUNT(*) FROM prompts
                WHERE status = 'completed' AND date(updated_at) = ?
            """, (today,))
            stats["completed_today"] = cursor.fetchone()[0]
            
            return stats
    
    def search(self, query: str, limit: int = 20) -> List[Prompt]:
        """Search prompts by text"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM prompts 
                WHERE text LIKE ? OR result LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit))
            return [self._row_to_prompt(row) for row in cursor.fetchall()]
    
    def _row_to_prompt(self, row: sqlite3.Row) -> Prompt:
        """Convert a database row to a Prompt object"""
        return Prompt(
            id=row["id"],
            text=row["text"],
            category=PromptCategory(row["category"]),
            priority=row["priority"],
            confidence=row["confidence"],
            impact=row["impact"],
            status=PromptStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=row["result"],
            result_quality=row["result_quality"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            template_id=row["template_id"],
            parent_id=row["parent_id"],
        )
