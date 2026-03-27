from datetime import datetime
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class SpecDocument(BaseModel):
    """Base model for all OpenSpec documents."""

    title: str = Field(..., description="Title of the document")
    version: str = Field(default="1.0", description="Version of the document")
    file_path: Optional[Path] = Field(
        default=None, description="File path where the document is stored"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="Last update timestamp"
    )

    def touch(self) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = datetime.now()
