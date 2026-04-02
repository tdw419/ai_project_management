"""
Trust Boundary - Protects critical files from pi agent corruption.

Snapshot hashes before an agent run, verify after. If violated,
auto-revert via git and report which files were touched.

Uses only stdlib (hashlib, pathlib). No external deps.
"""

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TrustBoundary:
    """Enforces a trust boundary for specified protected files."""

    protected_files: List[str]          # relative paths from base_path
    base_path: Path
    _hashes: Dict[str, Optional[str]] = field(default_factory=dict)
    _locked: bool = field(default=False)

    def __post_init__(self):
        self.base_path = Path(self.base_path).resolve()

    @staticmethod
    def _sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def lock(self) -> None:
        """Snapshot hashes of all protected files."""
        self._hashes = {}
        for rel in self.protected_files:
            full = self.base_path / rel
            if full.exists() and full.is_file():
                self._hashes[rel] = self._sha256(full)
            else:
                self._hashes[rel] = None
        self._locked = True

    def verify(self) -> bool:
        """True if all protected files are unchanged since lock()."""
        if not self._locked:
            raise RuntimeError("Call lock() before verify()")
        for rel, expected in self._hashes.items():
            full = self.base_path / rel
            if expected is None:
                if full.exists():
                    return False
                continue
            if not full.exists():
                return False
            if self._sha256(full) != expected:
                return False
        return True

    def get_violations(self) -> List[str]:
        """Return list of relative paths that were modified/deleted/created."""
        if not self._locked:
            raise RuntimeError("Call lock() before get_violations()")
        violations = []
        for rel, expected in self._hashes.items():
            full = self.base_path / rel
            if expected is None:
                if full.exists():
                    violations.append(rel)
                continue
            if not full.exists():
                violations.append(rel)
                continue
            if self._sha256(full) != expected:
                violations.append(rel)
        return violations

    def revert(self) -> bool:
        """Git checkout all violated files to restore their locked state.

        Returns True if revert succeeded, False otherwise.
        """
        violations = self.get_violations()
        if not violations:
            return True

        try:
            subprocess.run(
                ["git", "checkout", "--"] + violations,
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def is_protected(self, file_path: Path) -> bool:
        """Check if an absolute path maps to a protected file."""
        try:
            rel = Path(file_path).resolve().relative_to(self.base_path)
            return str(rel) in self.protected_files
        except ValueError:
            return False


@dataclass
class FullTreeTrust:
    """Trust boundary for an entire project tree.

    Snapshots ALL files recursively. Catches any change the pi agent makes.
    Use this when you want to know exactly what changed, then decide
    whether to keep or revert.
    """

    base_path: Path
    _hashes: Dict[str, str] = field(default_factory=dict)
    _locked: bool = field(default=False)

    # Dirs to skip during snapshot
    ignore_dirs = {
        "node_modules", ".git", "venv", ".venv", "build", "dist",
        "output", "target", "__pycache__", ".pytest_cache", ".ruff_cache",
        ".mypy_cache", ".tox", "egg-info",
    }

    def __post_init__(self):
        self.base_path = Path(self.base_path).resolve()

    def lock(self) -> int:
        """Snapshot all files. Returns count of files hashed."""
        self._hashes = {}
        for root, dirs, files in os.walk(self.base_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            for fname in files:
                full = Path(root) / fname
                try:
                    rel = str(full.relative_to(self.base_path))
                    self._hashes[rel] = self._sha256(full)
                except (OSError, PermissionError):
                    continue
        self._locked = True
        return len(self._hashes)

    def diff(self) -> Dict[str, str]:
        """Compare current tree to locked state.

        Returns dict mapping relative paths to change type:
          "modified", "added", "deleted"
        """
        if not self._locked:
            raise RuntimeError("Call lock() before diff()")

        changes: Dict[str, str] = {}

        # Check for modified/deleted
        current_paths = set()
        for root, dirs, files in os.walk(self.base_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            for fname in files:
                full = Path(root) / fname
                try:
                    rel = str(full.relative_to(self.base_path))
                    current_paths.add(rel)
                    if rel in self._hashes:
                        if self._sha256(full) != self._hashes[rel]:
                            changes[rel] = "modified"
                    else:
                        changes[rel] = "added"
                except (OSError, PermissionError):
                    continue

        # Check for deleted
        for rel in self._hashes:
            if rel not in current_paths:
                changes[rel] = "deleted"

        return changes

    def revert_all(self) -> bool:
        """Git checkout entire tree back to last commit."""
        try:
            subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            # Clean untracked files too
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=self.base_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
