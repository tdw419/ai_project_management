from enum import Enum
from typing import List
from pydantic import BaseModel, Field
from .base import SpecDocument


class RequirementStrength(str, Enum):
    """RFC 2119 requirement strengths."""

    MUST = "MUST"
    SHALL = "SHALL"
    SHOULD = "SHOULD"
    MAY = "MAY"


class Scenario(BaseModel):
    """A given-when-then scenario."""

    given: str = Field(..., description="The initial context or precondition")
    when: str = Field(..., description="The action or event")
    then: str = Field(..., description="The expected outcome")


class Requirement(BaseModel):
    """A single requirement."""

    id: str = Field(..., description="Unique identifier for the requirement")
    capability: str = Field(
        ..., description="The capability this requirement addresses"
    )
    strength: RequirementStrength = Field(
        ..., description="The strength of the requirement (MUST, SHALL, SHOULD, MAY)"
    )
    description: str = Field(..., description="Detailed description of the requirement")
    scenarios: List[Scenario] = Field(
        default_factory=list, description="Scenarios that illustrate the requirement"
    )


class RequirementsDocument(SpecDocument):
    """Model for OpenSpec requirements documents."""

    requirements: List[Requirement] = Field(
        default_factory=list, description="List of requirements"
    )

    def to_markdown(self) -> str:
        """Convert the requirements document to markdown format."""
        lines = ["## Requirements\n"]

        if not self.requirements:
            lines.append("*No requirements defined.*\n")
            return "".join(lines)

        for req in self.requirements:
            lines.extend(
                [
                    f"### {req.id}: {req.description}\n",
                    f"- **Capability**: {req.capability}\n",
                    f"- **Strength**: {req.strength.value}\n",
                ]
            )

            if req.scenarios:
                lines.append("- **Scenarios**:\n")
                for scenario in req.scenarios:
                    lines.extend(
                        [
                            f"  - **Given**: {scenario.given}\n",
                            f"  - **When**: {scenario.when}\n",
                            f"  - **Then**: {scenario.then}\n",
                        ]
                    )
            lines.append("\n")

        return "".join(lines)
