#!/usr/bin/env python3
"""
RAG World Model - Dynamic Context Injection from Git Diffs

Phase 1.1 of AIPM Roadmap: Implements "Groundedness v2" by automatically
updating CTRM context based on codebase changes.

How it works:
1. Post-commit hook triggers this module
2. Git diff extracted for latest commit
3. Diff analyzed and converted to semantic context
4. Context injected into CTRM as "world_model" truths
5. Future prompts get enriched with current codebase state
"""

import subprocess
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class CodeChange:
    """Represents a semantic code change"""
    file_path: str
    change_type: str  # "added", "modified", "deleted", "renamed"
    summary: str
    functions_added: List[str] = field(default_factory=list)
    functions_removed: List[str] = field(default_factory=list)
    classes_added: List[str] = field(default_factory=list)
    classes_removed: List[str] = field(default_factory=list)
    imports_added: List[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0


class RAGWorldModel:
    """
    RAG-based World Model for dynamic context injection.
    
    Monitors git changes and maintains a "living" view of the codebase
    that gets injected into prompts for better groundedness.
    """
    
    # Patterns for extracting semantic info
    FUNC_PATTERN = re.compile(r'^\+?\s*(?:def|async\s+def|fn|pub\s+fn|function)\s+(\w+)')
    CLASS_PATTERN = re.compile(r'^\+?\s*(?:class|struct|interface|impl)\s+(\w+)')
    IMPORT_PATTERN = re.compile(r'^\+?\s*(?:import|from|use|#include)\s+([\w\.\/]+)')
    
    def __init__(self, repo_path: Path, ctrm_db=None):
        self.repo_path = Path(repo_path)
        self.ctrm_db = ctrm_db
        self._last_commit: Optional[str] = None
        
    def get_latest_commit(self) -> str:
        """Get the latest commit hash"""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    
    def get_diff_for_commit(self, commit: str) -> str:
        """Get the diff for a specific commit"""
        result = subprocess.run(
            ["git", "show", "--stat", "-p", commit],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else ""
    
    def get_changed_files(self, commit: str) -> List[str]:
        """Get list of files changed in a commit"""
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return []
        return [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
    
    def analyze_file_diff(self, file_path: str, diff_content: str) -> CodeChange:
        """Analyze a file diff to extract semantic changes"""
        change = CodeChange(
            file_path=file_path,
            change_type="modified",
            summary="",
        )
        
        lines = diff_content.split('\n')
        current_hunk = []
        
        for line in lines:
            if line.startswith('+++') or line.startswith('---'):
                continue
            if line.startswith('@@'):
                # New hunk, process previous
                if current_hunk:
                    self._analyze_hunk(change, current_hunk)
                current_hunk = []
                continue
            
            if line.startswith('+') and not line.startswith('+++'):
                change.lines_added += 1
                current_hunk.append(line)
                
                # Extract functions
                match = self.FUNC_PATTERN.match(line)
                if match:
                    change.functions_added.append(match.group(1))
                
                # Extract classes
                match = self.CLASS_PATTERN.match(line)
                if match:
                    change.classes_added.append(match.group(1))
                
                # Extract imports
                match = self.IMPORT_PATTERN.match(line)
                if match:
                    change.imports_added.append(match.group(1))
                    
            elif line.startswith('-') and not line.startswith('---'):
                change.lines_removed += 1
                
                # Check for removed functions
                match = self.FUNC_PATTERN.match(line)
                if match:
                    change.functions_removed.append(match.group(1))
                
                match = self.CLASS_PATTERN.match(line)
                if match:
                    change.classes_removed.append(match.group(1))
        
        # Process last hunk
        if current_hunk:
            self._analyze_hunk(change, current_hunk)
        
        # Determine change type
        if change.lines_added > 0 and change.lines_removed == 0:
            change.change_type = "added"
        elif change.lines_added == 0 and change.lines_removed > 0:
            change.change_type = "deleted"
        
        # Generate summary
        change.summary = self._generate_summary(change)
        
        return change
    
    def _analyze_hunk(self, change: CodeChange, hunk: List[str]) -> None:
        """Analyze a diff hunk for semantic meaning"""
        # Future: Add more sophisticated analysis
        pass
    
    def _generate_summary(self, change: CodeChange) -> str:
        """Generate a human-readable summary of the change"""
        parts = []
        
        if change.functions_added:
            parts.append(f"Added functions: {', '.join(change.functions_added[:5])}")
        if change.functions_removed:
            parts.append(f"Removed functions: {', '.join(change.functions_removed[:5])}")
        if change.classes_added:
            parts.append(f"Added classes: {', '.join(change.classes_added[:5])}")
        if change.classes_removed:
            parts.append(f"Removed classes: {', '.join(change.classes_removed[:5])}")
        if change.imports_added:
            parts.append(f"New dependencies: {', '.join(change.imports_added[:3])}")
        
        if not parts:
            parts.append(f"+{change.lines_added}/-{change.lines_removed} lines")
        
        return "; ".join(parts)
    
    def process_commit(self, commit: Optional[str] = None) -> List[CodeChange]:
        """Process a commit and extract all semantic changes"""
        if commit is None:
            commit = self.get_latest_commit()
        
        if commit == self._last_commit:
            return []  # Already processed
        
        self._last_commit = commit
        changed_files = self.get_changed_files(commit)
        full_diff = self.get_diff_for_commit(commit)
        
        changes = []
        for file_path in changed_files:
            # Extract diff for this file
            file_diff = self._extract_file_diff(file_path, full_diff)
            if file_diff:
                change = self.analyze_file_diff(file_path, file_diff)
                changes.append(change)
        
        return changes
    
    def _extract_file_diff(self, file_path: str, full_diff: str) -> str:
        """Extract the diff section for a specific file"""
        lines = full_diff.split('\n')
        result = []
        in_file = False
        
        for line in lines:
            if line.startswith('diff --git'):
                # Check if this is our file
                if file_path in line:
                    in_file = True
                    result = [line]
                else:
                    in_file = False
            elif in_file:
                result.append(line)
        
        return '\n'.join(result)
    
    def generate_world_context(self, changes: List[CodeChange], max_items: int = 20) -> str:
        """Generate context string for injection into prompts"""
        if not changes:
            return ""
        
        lines = ["## Recent Codebase Changes\n"]
        lines.append("The following changes were made to the codebase:\n")
        
        # Group by change type
        by_type: Dict[str, List[CodeChange]] = {}
        for change in changes[:max_items]:
            by_type.setdefault(change.change_type, []).append(change)
        
        for change_type, type_changes in by_type.items():
            lines.append(f"### {change_type.title()} Files")
            for change in type_changes:
                lines.append(f"- `{change.file_path}`: {change.summary}")
            lines.append("")
        
        # Add function/class summary
        all_funcs = []
        all_classes = []
        for change in changes:
            all_funcs.extend(change.functions_added)
            all_classes.extend(change.classes_added)
        
        if all_funcs:
            lines.append(f"### New Functions: {', '.join(all_funcs[:10])}")
        if all_classes:
            lines.append(f"### New Classes: {', '.join(all_classes[:10])}")
        
        return '\n'.join(lines)
    
    def inject_to_ctrm(self, changes: List[CodeChange]) -> int:
        """Inject changes into CTRM as world_model truths"""
        if not self.ctrm_db:
            return 0
        
        injected = 0
        for change in changes:
            truth_id = hashlib.md5(
                f"{change.file_path}:{datetime.now().date()}".encode()
            ).hexdigest()[:12]
            
            self.ctrm_db.add_truth(
                id=f"world_model_{truth_id}",
                content=change.summary,
                category="world_model",  # RAG-based context
                confidence=0.9,
                source="rag_world_model",
                tags=["world_model", "git_diff", change.change_type],
                metadata={
                    "file_path": change.file_path,
                    "lines_added": change.lines_added,
                    "lines_removed": change.lines_removed,
                    "functions_added": change.functions_added,
                    "classes_added": change.classes_added,
                }
            )
            injected += 1
        
        return injected
    
    def get_context_for_prompt(self, max_age_hours: int = 24) -> str:
        """Get recent world model context for prompt injection"""
        if not self.ctrm_db:
            return ""
        
        # Query recent world_model truths
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        
        # This would query CTRM for recent world_model entries
        # For now, return placeholder
        truths = self.ctrm_db.query_by_tag("world_model", limit=20)
        
        if not truths:
            return ""
        
        lines = ["## Current Codebase State\n"]
        for truth in truths:
            lines.append(f"- {truth.content}")
        
        return '\n'.join(lines)


def create_git_hook(repo_path: Path) -> str:
    """Create a post-commit hook that triggers RAG update"""
    hook_content = '''#!/bin/bash
# AIPM RAG World Model - Post-commit hook
# Automatically updates CTRM with codebase changes

cd "$(git rev-parse --show-toplevel)"

# Run RAG update in background to not block commit
python3 -c "
import sys
sys.path.insert(0, '.')
from aipm.rag_context import RAGWorldModel
from aipm.config import CTRM_DB
from aipm.ctrm.database import CTRMDatabase

ctrm = CTRMDatabase(CTRM_DB)
rag = RAGWorldModel('.', ctrm)
changes = rag.process_commit()
if changes:
    rag.inject_to_ctrm(changes)
    print(f'[RAG] Injected {len(changes)} changes into CTRM')
" &

# Don't wait for background process
disown
'''
    return hook_content


# CLI interface
if __name__ == "__main__":
    import sys
    
    repo_path = Path.cwd()
    
    # Try to connect to CTRM
    try:
        from aipm.ctrm.database import CTRMDatabase
        from aipm.config import CTRM_DB
        ctrm = CTRMDatabase(CTRM_DB)
    except ImportError:
        ctrm = None
        print("Warning: CTRM not available, running in dry-run mode")
    
    rag = RAGWorldModel(repo_path, ctrm)
    
    # Process latest commit
    changes = rag.process_commit()
    
    if not changes:
        print("No changes found or commit already processed")
        sys.exit(0)
    
    print(f"\n📊 Analyzed {len(changes)} file changes:\n")
    
    for change in changes:
        print(f"  {change.change_type.upper()}: {change.file_path}")
        print(f"    Summary: {change.summary}")
        print(f"    Lines: +{change.lines_added}/-{change.lines_removed}")
        if change.functions_added:
            print(f"    Functions: {', '.join(change.functions_added)}")
        print()
    
    # Generate context
    context = rag.generate_world_context(changes)
    print("\n" + "="*60)
    print("Generated Context for Prompt Injection:")
    print("="*60)
    print(context)
    
    # Inject to CTRM if available
    if ctrm:
        injected = rag.inject_to_ctrm(changes)
        print(f"\n✅ Injected {injected} truths into CTRM")
