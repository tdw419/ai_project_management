from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import hashlib


@dataclass
class TrustBoundary:
    """Enforces a trust boundary for specified protected files."""

    protected_files: List[str]
    base_path: Path
    _hashes: Dict[str, Optional[str]] = field(default_factory=dict)
    _locked: bool = field(default=False)

    def __post_init__(self):
        self.base_path = Path(self.base_path)

    def calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            SHA256 hash as a hexadecimal string

        Raises:
            FileNotFoundError: If the file does not exist
        """
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
                # If file doesn't exist yet, we'll store None and check later
                self._hashes[file_rel_path] = None
        self._locked = True

    def verify_integrity(self) -> bool:
        """Check if any protected files have been modified.

        Returns:
            True if all files are unchanged, False if any have been modified
        """
        if not self._locked:
            raise RuntimeError("Trust boundary must be locked before verification")

        for file_rel_path, expected_hash in self._hashes.items():
            file_path = self.base_path / file_rel_path

            # If file didn't exist when locked, check if it exists now
            if expected_hash is None:
                if file_path.exists():
                    # File now exists when it didn't before - this is a change
                    return False
                else:
                    # Still doesn't exist - OK
                    continue

            # File existed when locked
            if not file_path.exists():
                # File was deleted - this is a change
                return False

            current_hash = self.calculate_hash(file_path)
            if current_hash != expected_hash:
                # File has been modified
                return False

        return True

    def is_protected(self, file_path: Path) -> bool:
        """Check if a file is protected by the trust boundary.

        Args:
            file_path: Path to check

        Returns:
            True if the file is protected, False otherwise
        """
        try:
            # Make path relative to base_path
            rel_path = file_path.relative_to(self.base_path)
            return str(rel_path) in self.protected_files
        except ValueError:
            # file_path is not relative to base_path
            return False

    def get_violations(self) -> List[str]:
        """Get list of protected files that have been violated (modified/deleted/new).

        Returns:
            List of file paths that violate the trust boundary
        """
        if not self._locked:
            raise RuntimeError(
                "Trust boundary must be locked before checking violations"
            )

        violations = []
        for file_rel_path, expected_hash in self._hashes.items():
            file_path = self.base_path / file_rel_path

            # If file didn't exist when locked
            if expected_hash is None:
                if file_path.exists():
                    # File now exists when it didn't before
                    violations.append(str(file_path))
                continue

            # File existed when locked
            if not file_path.exists():
                # File was deleted
                violations.append(str(file_path))
                continue

            current_hash = self.calculate_hash(file_path)
            if current_hash != expected_hash:
                # File has been modified
                violations.append(str(file_path))

        return violations
