"""
CTRM Database - Contextual Truth Reference Model

SQLite-backed storage for truths, facts, and learned patterns.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class TruthCategory(str, Enum):
    """Categories of truths"""
    FACT = "fact"
    PATTERN = "pattern"
    RULE = "rule"
    INSIGHT = "insight"
    DECISION = "decision"
    PROMPT = "prompt"
    RESULT = "result"


@dataclass
class Truth:
    """A truth in the CTRM database"""
    id: str
    content: str
    category: TruthCategory
    confidence: float = 0.5
    source: str = "unknown"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category.value,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "tags": self.tags,
        }


class CTRMDatabase:
    """
    Contextual Truth Reference Model database.
    
    Stores and manages truths with confidence scoring.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".aipm" / "data" / "truths.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS truths (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    source TEXT DEFAULT 'unknown',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT,
                    tags TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category ON truths(category)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_confidence ON truths(confidence)
            """)
            
            # FTS for full-text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS truths_fts USING fts5(
                    id, content, tags
                )
            """)
    
    def add(self, truth: Truth) -> None:
        """Add a truth to the database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO truths (
                    id, content, category, confidence, source,
                    created_at, updated_at, metadata, tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                truth.id,
                truth.content,
                truth.category.value,
                truth.confidence,
                truth.source,
                truth.created_at.isoformat(),
                truth.updated_at.isoformat(),
                json.dumps(truth.metadata),
                json.dumps(truth.tags),
            ))
            
            # Update FTS index
            conn.execute("""
                INSERT OR REPLACE INTO truths_fts (id, content, tags)
                VALUES (?, ?, ?)
            """, (truth.id, truth.content, " ".join(truth.tags)))
    
    def get(self, truth_id: str) -> Optional[Truth]:
        """Get a truth by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM truths WHERE id = ?", (truth_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_truth(row)
        return None
    
    def update(self, truth: Truth) -> None:
        """Update a truth"""
        truth.updated_at = datetime.now()
        self.add(truth)
    
    def delete(self, truth_id: str) -> None:
        """Delete a truth"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM truths WHERE id = ?", (truth_id,))
            conn.execute("DELETE FROM truths_fts WHERE id = ?", (truth_id,))
    
    def search(self, query: str, limit: int = 20) -> List[Truth]:
        """Search truths by content"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT t.* FROM truths t
                JOIN truths_fts fts ON t.id = fts.id
                WHERE truths_fts MATCH ?
                ORDER BY t.confidence DESC
                LIMIT ?
            """, (query, limit))
            return [self._row_to_truth(row) for row in cursor.fetchall()]
    
    def get_by_category(
        self,
        category: TruthCategory,
        limit: int = 100,
        min_confidence: float = 0.0,
    ) -> List[Truth]:
        """Get truths by category"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM truths
                WHERE category = ? AND confidence >= ?
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
            """, (category.value, min_confidence, limit))
            return [self._row_to_truth(row) for row in cursor.fetchall()]
    
    def get_high_confidence(self, threshold: float = 0.8, limit: int = 100) -> List[Truth]:
        """Get truths with high confidence"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM truths
                WHERE confidence >= ?
                ORDER BY confidence DESC
                LIMIT ?
            """, (threshold, limit))
            return [self._row_to_truth(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        with sqlite3.connect(self.db_path) as conn:
            stats = {}
            
            # Total count
            cursor = conn.execute("SELECT COUNT(*) FROM truths")
            stats["total"] = cursor.fetchone()[0]
            
            # Count by category
            cursor = conn.execute("""
                SELECT category, COUNT(*) as count
                FROM truths
                GROUP BY category
            """)
            stats["by_category"] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Average confidence
            cursor = conn.execute("SELECT AVG(confidence) FROM truths")
            stats["avg_confidence"] = cursor.fetchone()[0] or 0.0
            
            # High confidence count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM truths WHERE confidence >= 0.8"
            )
            stats["high_confidence"] = cursor.fetchone()[0]
            
            return stats
    
    def _row_to_truth(self, row: sqlite3.Row) -> Truth:
        """Convert a database row to a Truth object"""
        return Truth(
            id=row["id"],
            content=row["content"],
            category=TruthCategory(row["category"]),
            confidence=row["confidence"],
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            tags=json.loads(row["tags"]) if row["tags"] else [],
        )
