"""
Template installer -- sets up GitHub issue templates and AGENTS.md
in a project directory.
"""

from pathlib import Path
from typing import List


TEMPLATES_DIR = Path(__file__).parent / "templates"


def install_templates(project_path: Path, force: bool = False) -> List[str]:
    """Install GitHub issue templates and AGENTS.md into a project.

    Returns list of files created.
    """
    project_path = Path(project_path).resolve()
    installed: List[str] = []

    # .github/ISSUE_TEMPLATE/
    issue_dir = project_path / ".github" / "ISSUE_TEMPLATE"
    issue_dir.mkdir(parents=True, exist_ok=True)

    for template_file in TEMPLATES_DIR.glob("*.yml"):
        dst = issue_dir / template_file.name
        if not dst.exists() or force:
            dst.write_text(template_file.read_text())
            installed.append(str(dst.relative_to(project_path)))

    # AGENTS.md
    agents_src = TEMPLATES_DIR / "AGENTS.md"
    agents_dst = project_path / "AGENTS.md"
    if agents_src.exists() and (not agents_dst.exists() or force):
        agents_dst.write_text(agents_src.read_text())
        installed.append("AGENTS.md")

    return installed
