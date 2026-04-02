import os
from pathlib import Path
from typing import List, Optional
from .config import ProjectConfig

class ProjectScanner:
    """Scans for projects in a directory tree."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).expanduser().resolve()
        self.ignore_dirs = {
            "node_modules", ".git", "venv", ".venv", "build", "dist", 
            "output", "target", "__pycache__", ".pytest_cache", ".ruff_cache",
            ".venv_copy_lancedb"
        }

    def scan(self) -> List[ProjectConfig]:
        """Find all projects with a project.yaml or auto-detect them.
        
        Only scans immediate subdirectories of root_path (one level deep).
        Deeper scanning into project internals causes false positives.
        """
        projects = []
        
        # 1. Check root itself
        root_files = os.listdir(self.root_path) if self.root_path.exists() else []
        if "project.yaml" in root_files:
            try:
                projects.append(ProjectConfig.from_yaml(self.root_path / "project.yaml"))
            except Exception as e:
                print(f"Error loading {self.root_path / 'project.yaml'}: {e}")
        elif self._is_project_root(self.root_path, root_files):
            config = self._auto_detect(self.root_path, root_files)
            if config:
                projects.append(config)

        # 2. Scan immediate subdirectories only
        if self.root_path.exists():
            for entry in sorted(self.root_path.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith('.') or entry.name in self.ignore_dirs:
                    continue
                
                try:
                    files = os.listdir(entry)
                except PermissionError:
                    continue

                # project.yaml takes priority
                if "project.yaml" in files:
                    try:
                        projects.append(ProjectConfig.from_yaml(entry / "project.yaml"))
                        continue
                    except Exception as e:
                        print(f"Error loading {entry / 'project.yaml'}: {e}")

                # Auto-detect
                if self._is_project_root(entry, files):
                    config = self._auto_detect(entry, files)
                    if config:
                        projects.append(config)
        
        return projects

    def _is_project_root(self, path: Path, files: List[str]) -> bool:
        """Check if a directory looks like a project root."""
        markers = {
            "Cargo.toml", "go.mod", "package.json", "pyproject.toml", 
            "requirements.txt", "Makefile", ".git", "interpreter.glyph",
            "README.md"
        }
        return any(m in files for m in markers)

    def _auto_detect(self, path: Path, files: List[str]) -> Optional[ProjectConfig]:
        """Attempt to auto-detect a project at a given path."""
        markers = {
            "Cargo.toml": "rust",
            "go.mod": "go",
            "package.json": "javascript/typescript",
            "pyproject.toml": "python",
            "requirements.txt": "python",
            "interpreter.glyph": "glyph",
            "Makefile": "generic",
            ".git": "generic",
            "README.md": "generic"
        }

        detected_lang = "unknown"
        for marker, lang in markers.items():
            if marker in files:
                detected_lang = lang
                break
        
        return ProjectConfig(
            name=path.name,
            path=str(path),
            language=detected_lang
        )
