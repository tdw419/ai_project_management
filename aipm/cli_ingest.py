#!/usr/bin/env python3
"""CLI tool for ingesting prompts into CTRM database."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aipm.config import CTRM_DB
import sqlite3
import hashlib

def ingest_file(filepath: str, source: str = "manual", priority: int = 5):
    """Ingest prompts from a file into the queue."""
    with open(filepath, 'r') as f:
        prompts = [line.strip() for line in f if line.strip()]
    
    conn = sqlite3.connect(CTRM_DB)
    cursor = conn.cursor()
    
    count = 0
    for prompt in prompts:
        prompt_id = f"prompt_{hashlib.md5(prompt.encode()).hexdigest()[:8]}"
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO prompt_queue 
                (id, prompt, source, priority, status, queued_at)
                VALUES (?, ?, ?, ?, 'pending', datetime('now'))
            """, (prompt_id, prompt, source, priority))
            count += 1
        except Exception as e:
            print(f"Error: {e}")
    
    conn.commit()
    conn.close()
    print(f"Ingested {count} prompts from {filepath}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m aipm.cli_ingest <file> [source] [priority]")
        sys.exit(1)
    
    filepath = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else "manual"
    priority = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    
    ingest_file(filepath, source, priority)
