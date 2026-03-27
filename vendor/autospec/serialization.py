import yaml
from pathlib import Path
from typing import TypeVar, Union, Dict, Any
from .models.base import SpecDocument
from .models.proposal import ProposalDocument
from .models.requirements import RequirementsDocument
from .models.design import DesignDocument
from .models.tasks import TaskDocument


def model_to_dict(model: SpecDocument) -> Dict[str, Any]:
    """Convert a Pydantic model to a dictionary, handling special types.

    This converts:
    - Path objects to strings
    - Enum objects to their values
    - nested models recursively

    Args:
        model: The Pydantic model to convert

    Returns:
        A dictionary representation of the model
    """
    # Use model_dump with custom handlers for specific types
    return model.model_dump(
        mode="json",  # This handles enums and other special types correctly
        exclude_none=False,  # We want to keep None values
    )


T = TypeVar("T", bound=SpecDocument)

# Mapping of document types to their model classes
DOCUMENT_TYPE_MAP = {
    "proposal": ProposalDocument,
    "requirements": RequirementsDocument,
    "design": DesignDocument,
    "tasks": TaskDocument,
}


def save_document(document: SpecDocument) -> None:
    """Save a document to its file path.

    Args:
        document: The document to save

    Raises:
        ValueError: If the document has no file_path set
    """
    if document.file_path is None:
        raise ValueError("Document must have a file_path set to be saved")

    # Ensure the parent directory exists
    document.file_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict and save as YAML
    document_dict = model_to_dict(document)

    # Convert Path objects to strings for YAML serialization
    if "file_path" in document_dict and document_dict["file_path"] is not None:
        document_dict["file_path"] = str(document_dict["file_path"])

    with open(document.file_path, "w") as f:
        yaml.dump(document_dict, f, default_flow_style=False)

    # Update the timestamp
    document.touch()


def load_document(file_path: Union[str, Path], doc_type: str) -> SpecDocument:
    """Load a document from a file.

    Args:
        file_path: Path to the document file
        doc_type: Type of document to load (proposal, requirements, design, tasks)

    Returns:
        The loaded document

    Raises:
        ValueError: If doc_type is not recognized
        FileNotFoundError: If the file does not exist
    """
    if doc_type not in DOCUMENT_TYPE_MAP:
        raise ValueError(
            f"Unknown document type: {doc_type}. Must be one of {list(DOCUMENT_TYPE_MAP.keys())}"
        )

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Document file not found: {file_path}")

    model_class = DOCUMENT_TYPE_MAP[doc_type]

    with open(file_path, "r") as f:
        document_dict = yaml.safe_load(f)

    # Convert file_path string back to Path object if present
    if "file_path" in document_dict and document_dict["file_path"] is not None:
        document_dict["file_path"] = Path(document_dict["file_path"])

    return model_class(**document_dict)


def _parse_proposal(markdown_content: str) -> dict:
    """Parse proposal markdown content into a dictionary.

    This is a simplified parser that extracts the main sections.
    In a full implementation, this would be more robust.

    Args:
        markdown_content: The markdown content to parse

    Returns:
        Dictionary with the parsed content
    """
    # This is a placeholder implementation
    # A real implementation would parse the markdown structure
    # For now, we'll return a basic structure
    return {
        "title": "Parsed Proposal",
        "why": "TODO: Parse why section",
        "whats_changing": "TODO: Parse what's changing section",
        "success_criteria": [],
        "risks": [],
    }


def _parse_requirements(markdown_content: str) -> dict:
    """Parse requirements markdown content into a dictionary.

    Args:
        markdown_content: The markdown content to parse

    Returns:
        Dictionary with the parsed content
    """
    # Placeholder implementation
    return {"title": "Parsed Requirements", "requirements": []}


def _parse_design(markdown_content: str) -> dict:
    """Parse design markdown content into a dictionary.

    Args:
        markdown_content: The markdown content to parse

    Returns:
        Dictionary with the parsed content
    """
    # Placeholder implementation
    return {
        "title": "Parsed Design",
        "architecture_overview": "TODO: Parse architecture overview",
        "components": [],
        "data_flow": "",
        "migration_path": "",
        "file_changes": [],
    }


def _parse_tasks(markdown_content: str) -> dict:
    """Parse tasks markdown content into a dictionary.

    Args:
        markdown_content: The markdown content to parse

    Returns:
        Dictionary with the parsed content
    """
    # Placeholder implementation
    return {"title": "Parsed Tasks", "tasks": []}
