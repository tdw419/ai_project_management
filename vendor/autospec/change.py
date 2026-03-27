from enum import Enum
from pathlib import Path
import time
import yaml


class ChangeStatus(str, Enum):
    """Status of a change."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


def generate_change_id(slug: str) -> str:
    """Generate a unique change ID from a slug and timestamp.

    Args:
        slug: A human-readable identifier for the change

    Returns:
        A unique ID in the format "<slug>-<timestamp>"
    """
    timestamp = int(time.time())
    return f"{slug}-{timestamp}"


class Change:
    """Represents a change in the OpenSpec system."""

    def __init__(self, id: str, title: str, status: ChangeStatus, base_path: Path):
        self.id = id
        self.title = title
        self.status = status
        self.base_path = base_path
        self.changes_path = base_path / "openspec" / "changes" / id

    def create_directory(self) -> None:
        """Create the directory structure for this change."""
        self.changes_path.mkdir(parents=True, exist_ok=True)
        (self.changes_path / "specs").mkdir(exist_ok=True)

    def get_document_path(self, document_type: str) -> Path:
        """Get the file path for a document of the given type.

        Args:
            document_type: The type of document (proposal, requirements, design, tasks)

        Returns:
            The Path where the document should be stored
        """
        return self.changes_path / f"{document_type}.md"

    def save_status(self) -> None:
        """Save the change status to a YAML file."""
        status_file = self.changes_path / "status.yaml"
        status_data = {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
        }
        with open(status_file, "w") as f:
            yaml.dump(status_data, f, default_flow_style=False)

    def load_status(self) -> None:
        """Load the change status from a YAML file."""
        status_file = self.changes_path / "status.yaml"
        if status_file.exists():
            with open(status_file, "r") as f:
                status_data = yaml.safe_load(f)
            self.title = status_data.get("title", self.title)
            self.status = ChangeStatus(status_data.get("status", "draft"))


def list_changes(base_path: Path) -> list[Change]:
    """List all changes in the openspec/changes directory.

    Args:
        base_path: The base path of the project

    Returns:
        A list of Change objects, sorted by ID
    """
    changes_dir = base_path / "openspec" / "changes"
    if not changes_dir.exists():
        return []

    changes = []
    for change_dir in changes_dir.iterdir():
        if change_dir.is_dir():
            change = Change(
                id=change_dir.name,
                title="",
                status=ChangeStatus.DRAFT,
                base_path=base_path,
            )
            change.load_status()
            changes.append(change)

    return sorted(changes, key=lambda c: c.id)
