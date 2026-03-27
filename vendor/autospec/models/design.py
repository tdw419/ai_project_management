from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from .base import SpecDocument


class FileAction(str, Enum):
    """Actions that can be performed on files."""

    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


class Component(BaseModel):
    """A component in the system design."""

    name: str = Field(..., description="Name of the component")
    responsibility: str = Field(
        ..., description="What the component is responsible for"
    )
    file_path: Optional[str] = Field(
        default=None, description="Primary file path for the component"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="List of component names this component depends on",
    )


class FileChange(BaseModel):
    """A change to be made to a file."""

    path: str = Field(..., description="File path to change")
    action: FileAction = Field(..., description="Action to perform on the file")
    description: str = Field(..., description="Description of the change")
    lines: Optional[int] = Field(
        default=None, description="Number of lines added/modified (if applicable)"
    )


class DesignDocument(SpecDocument):
    """Model for OpenSpec design documents."""

    architecture_overview: str = Field(
        ..., description="High-level overview of the system architecture"
    )
    components: List[Component] = Field(
        default_factory=list, description="Components in the system"
    )
    data_flow: str = Field(
        default="", description="Description of data flow through the system"
    )
    migration_path: str = Field(
        default="", description="How to migrate from the current state to this design"
    )
    file_changes: List[FileChange] = Field(
        default_factory=list,
        description="Specific file changes to implement this design",
    )

    def to_markdown(self) -> str:
        """Convert the design document to markdown format."""
        lines = [
            "## Architecture Overview\n",
            f"{self.architecture_overview}\n",
        ]

        if self.components:
            lines.extend(
                [
                    "## Components\n",
                    "\n",
                ]
            )
            for component in self.components:
                lines.extend(
                    [
                        f"### {component.name}\n",
                        f"- **Responsibility**: {component.responsibility}\n",
                    ]
                )
                if component.file_path:
                    lines.append(f"- **File Path**: {component.file_path}\n")
                if component.dependencies:
                    lines.append(
                        f"- **Dependencies**: {', '.join(component.dependencies)}\n"
                    )
                lines.append("\n")

        if self.data_flow:
            lines.extend(
                [
                    "## Data Flow\n",
                    f"{self.data_flow}\n",
                    "\n",
                ]
            )

        if self.migration_path:
            lines.extend(
                [
                    "## Migration Path\n",
                    f"{self.migration_path}\n",
                    "\n",
                ]
            )

        if self.file_changes:
            lines.extend(
                [
                    "## File Changes\n",
                    "\n",
                ]
            )
            for change in self.file_changes:
                lines.extend(
                    [
                        f"### {change.path}\n",
                        f"- **Action**: {change.action.value}\n",
                        f"- **Description**: {change.description}\n",
                    ]
                )
                if change.lines is not None:
                    lines.append(f"- **Lines**: {change.lines}\n")
                lines.append("\n")

        return "".join(lines)
