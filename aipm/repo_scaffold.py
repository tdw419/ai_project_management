"""
Repo Scaffolder -- create new projects that AIPM can immediately manage.

Flow:
  1. Create directory in repos/
  2. Write language-appropriate scaffold (go.mod, package.json, pyproject.toml, etc.)
  3. Write project.yaml
  4. git init + initial commit
  5. Optionally create GitHub remote via `gh repo create`
  6. Scanner picks it up automatically on next cycle
"""

import subprocess
import os
from pathlib import Path
from typing import Optional

REPOS_ROOT = Path(__file__).parent.parent / "repos"

LANGUAGES = {
    "python": {
        "files": {
            "pyproject.toml": """\
[project]
name = "{name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
            "tests/__init__.py": "",
            "tests/test_{safe_name}.py": """\
import pytest


def test_placeholder():
    assert True
""",
            "{safe_name}/__init__.py": "",
            "{safe_name}/main.py": "\"\"\"{name} entry point.\"\"\" \n",
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\ndist/\n*.egg-info/\n.pytest_cache/\n",
        },
        "test_command": "pytest",
        "test_parser": "pytest",
    },
    "go": {
        "files": {
            "go.mod": "module github.com/tdw419/{name}\n\ngo 1.25\n",
            "main.go": "package main\n\nimport \"fmt\"\n\nfunc main() {{\n\tfmt.Println(\"{name}\")\n}}\n",
            "{safe_name}_test.go": "package main\n\nimport \"testing\"\n\nfunc TestPlaceholder(t *testing.T) {{\n\t// placeholder\n}}\n",
            ".gitignore": "bin/\n*.exe\n",
        },
        "test_command": "go test ./...",
        "test_parser": "go",
    },
    "rust": {
        "files": {
            "Cargo.toml": '[package]\nname = "{safe_name}"\nversion = "0.1.0"\nedition = "2021"\n',
            "src/main.rs": "fn main() {{\n    println!(\"Hello, {name}!\");\n}}\n",
            "src/lib.rs": "",
            ".gitignore": "target/\n",
        },
        "test_command": "cargo test",
        "test_parser": "cargo",
    },
    "javascript": {
        "files": {
            "package.json": '{{\n  "name": "{name}",\n  "version": "1.0.0",\n  "description": "{description}",\n  "main": "index.js",\n  "scripts": {{\n    "test": "node --test"\n  }}\n}}\n',
            "index.js": f"// {{name}} entry point\n",
            "test/test.js": 'import {{ describe, it }} from "node:test";\nimport assert from "node:assert";\n\ndescribe("placeholder", () => {{\n  it("works", () => {{\n    assert.ok(true);\n  }});\n}});\n',
            ".gitignore": "node_modules/\n",
        },
        "test_command": "npm test",
        "test_parser": "regex",
    },
}


def scaffold_repo(
    name: str,
    language: str,
    description: str = "",
    github_private: bool = True,
    create_github: bool = True,
) -> Optional[Path]:
    """Create a new project directory with full scaffold.

    Args:
        name: Project name (used for dir, package, repo)
        language: python, go, rust, javascript
        description: Short description
        github_private: True = private repo, False = public
        create_github: Whether to create GitHub remote

    Returns:
        Path to the new project dir, or None on failure
    """
    language = language.lower()
    if language not in LANGUAGES:
        print(f"Unsupported language: {language}")
        print(f"Supported: {', '.join(LANGUAGES.keys())}")
        return None

    lang_config = LANGUAGES[language]
    safe_name = name.replace("-", "_")
    project_dir = REPOS_ROOT / name

    if project_dir.exists():
        print(f"ERROR: {project_dir} already exists")
        return None

    # Format all template files
    template_vars = {
        "name": name,
        "safe_name": safe_name,
        "description": description or f"{name} project",
    }

    print(f"Scaffolding {name} ({language})...")
    print(f"  Dir: {project_dir}")

    # Create files
    for rel_path, template in lang_config["files"].items():
        resolved_path = rel_path.format(**template_vars)
        file_path = project_dir / resolved_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = template.format(**template_vars)
        file_path.write_text(content)
        print(f"  Created {resolved_path}")

    # Write project.yaml
    project_yaml = (
        f"name: {name}\n"
        f"language: {language}\n"
        f"test_command: {lang_config['test_command']}\n"
        f"test_parser: {lang_config['test_parser']}\n"
        f"health_threshold: 3\n"
    )
    (project_dir / "project.yaml").write_text(project_yaml)
    print(f"  Created project.yaml")

    # README
    readme = f"# {name}\n\n{description or name}\n"
    (project_dir / "README.md").write_text(readme)

    # git init
    result = subprocess.run(
        ["git", "init"], cwd=str(project_dir),
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"  WARNING: git init failed: {result.stderr.strip()}")
        return project_dir

    # Initial commit
    subprocess.run(
        ["git", "add", "-A"], cwd=str(project_dir),
        capture_output=True, text=True, timeout=15,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial scaffold via AIPM"],
        cwd=str(project_dir),
        capture_output=True, text=True, timeout=15,
    )
    print(f"  Git initialized + initial commit")

    # Create GitHub remote
    if create_github:
        visibility = "--private" if github_private else "--public"
        result = subprocess.run(
            [
                "gh", "repo", "create", name,
                visibility,
                "--source", str(project_dir),
                "--push",
                "--description", description or name,
            ],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            repo_url = result.stdout.strip()
            print(f"  GitHub: {repo_url}")
        else:
            print(f"  WARNING: GitHub create failed: {result.stderr.strip()}")
            print(f"  Repo is local-only. You can add a remote later.")

    print(f"  Done! Scanner will discover it on next cycle.")
    return project_dir
