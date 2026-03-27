from typing import List
from pydantic import Field
from .base import SpecDocument


class ProposalDocument(SpecDocument):
    """Model for OpenSpec proposal documents."""

    why: str = Field(..., description="The rationale for the change")
    whats_changing: str = Field(..., description="What is being changed")
    success_criteria: List[str] = Field(
        default_factory=list, description="Criteria for determining success"
    )
    risks: List[str] = Field(
        default_factory=list, description="Potential risks or drawbacks"
    )

    def to_markdown(self) -> str:
        """Convert the proposal to markdown format."""
        lines = [
            "## Why\n",
            f"{self.why}\n",
            "\n## What Changes\n",
            f"{self.whats_changing}\n",
        ]

        if self.success_criteria:
            lines.extend(
                [
                    "\n## Success Criteria\n",
                ]
            )
            for criterion in self.success_criteria:
                lines.append(f"- {criterion}\n")
            lines.append("\n")

        if self.risks:
            lines.extend(
                [
                    "\n## Risks\n",
                ]
            )
            for risk in self.risks:
                lines.append(f"- {risk}\n")
            lines.append("\n")

        return "".join(lines)
