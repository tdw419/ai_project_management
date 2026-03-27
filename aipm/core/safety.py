"""
Safety Layer for Ouroboros

Prevents the AI from:
1. Modifying evaluation criteria (cheating)
2. Accessing files outside the workspace
3. Running dangerous commands
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional
import hashlib
import shutil


@dataclass
class TrustBoundary:
    """Enforces a trust boundary for specified protected files.

    Prevents the AI from "cheating" by modifying evaluation criteria.
    """

    protected_files: List[str]
    base_path: Path
    _hashes: Dict[str, Optional[str]] = field(default_factory=dict)
    _locked: bool = field(default=False)

    def __post_init__(self):
        self.base_path = Path(self.base_path)

    def calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def lock(self) -> None:
        """Record hashes for all protected files."""
        self._hashes = {}
        for file_rel_path in self.protected_files:
            file_path = self.base_path / file_rel_path
            if file_path.exists():
                self._hashes[file_rel_path] = self.calculate_hash(file_path)
            else:
                self._hashes[file_rel_path] = None
        self._locked = True
        print(f"🔒 Trust boundary locked: {len(self._hashes)} files protected")

    def verify_integrity(self) -> bool:
        """Check if any protected files have been modified."""
        if not self._locked:
            raise RuntimeError("Trust boundary must be locked before verification")

        for file_rel_path, expected_hash in self._hashes.items():
            file_path = self.base_path / file_rel_path

            if expected_hash is None:
                if file_path.exists():
                    return False
                continue

            if not file_path.exists():
                return False

            current_hash = self.calculate_hash(file_path)
            if current_hash != expected_hash:
                return False

        return True

    def get_violations(self) -> List[str]:
        """Get list of protected files that have been violated."""
        if not self._locked:
            raise RuntimeError("Trust boundary must be locked")

        violations = []
        for file_rel_path, expected_hash in self._hashes.items():
            file_path = self.base_path / file_rel_path

            if expected_hash is None:
                if file_path.exists():
                    violations.append(str(file_path))
                continue

            if not file_path.exists():
                violations.append(str(file_path))
                continue

            current_hash = self.calculate_hash(file_path)
            if current_hash != expected_hash:
                violations.append(str(file_path))

        return violations

    def is_protected(self, file_path: Path) -> bool:
        """Check if a file is protected."""
        try:
            abs_path = file_path.resolve()
            base_abs = self.base_path.resolve()
            rel_path = abs_path.relative_to(base_abs)
            return str(rel_path) in self.protected_files
        except ValueError:
            return False


@dataclass
class SafetyConfig:
    """Configuration for safety features."""

    # Files that CANNOT be modified by the AI (evaluation criteria, tests)
    protected_files: List[str] = field(default_factory=list)

    # Files that CAN be modified by the AI
    allowed_targets: List[str] = field(default_factory=list)

    # Create backup before each modification
    create_backup: bool = True

    # Maximum file size to modify (in bytes)
    max_file_size: int = 100_000  # 100KB

    # Disallowed patterns in code
    blocked_patterns: List[str] = field(default_factory=lambda: [
        "import os",
        "import subprocess",
        "import sys",
        "exec(",
        "eval(",
        "__import__",
        "open(",
    ])


class SafetyManager:
    """Manages all safety features for the Ouroboros loop."""

    def __init__(self, config: SafetyConfig, workspace_path: Path):
        self.config = config
        self.workspace_path = workspace_path
        self.trust_boundary = TrustBoundary(
            protected_files=config.protected_files,
            base_path=workspace_path
        )
        self._backup_dir = workspace_path / ".ouroboros" / "backups"

    def lock(self) -> None:
        """Lock the trust boundary before starting the loop."""
        self.trust_boundary.lock()

    def verify(self) -> bool:
        """Verify no protected files were modified."""
        return self.trust_boundary.verify_integrity()

    def get_violations(self) -> List[str]:
        """Get list of trust boundary violations."""
        return self.trust_boundary.get_violations()

    def can_modify(self, file_path: Path) -> bool:
        """Check if a file can be modified by the AI."""
        # Resolve to absolute path if relative
        if not file_path.is_absolute():
            abs_path = (self.workspace_path / file_path).resolve()
        else:
            abs_path = file_path.resolve()

        # Check if protected
        if self.trust_boundary.is_protected(abs_path):
            return False

        # Check if in allowed targets (if specified)
        if self.config.allowed_targets:
            try:
                rel_path = abs_path.relative_to(self.workspace_path.resolve())
                if str(rel_path) not in self.config.allowed_targets:
                    return False
            except ValueError:
                return False

        # Check file size
        if file_path.exists() and file_path.stat().st_size > self.config.max_file_size:
            return False

        return True

    def check_code_safety(self, code: str) -> List[str]:
        """Check code for blocked patterns."""
        violations = []
        for pattern in self.config.blocked_patterns:
            if pattern in code:
                violations.append(f"Blocked pattern found: {pattern}")
        return violations

    def backup_file(self, file_path: Path) -> Optional[Path]:
        """Create a backup of a file before modification."""
        if not self.config.create_backup:
            return None

        if not file_path.exists():
            return None

        self._backup_dir.mkdir(parents=True, exist_ok=True)

        import time
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        backup_path = self._backup_dir / backup_name

        shutil.copy2(file_path, backup_path)
        print(f"📦 Backup created: {backup_path}")

        return backup_path

    def restore_backup(self, backup_path: Path, target_path: Path) -> bool:
        """Restore a file from backup."""
        if not backup_path.exists():
            return False

        shutil.copy2(backup_path, target_path)
        print(f"♻️ Restored from backup: {backup_path}")
        return True
