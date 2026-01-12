"""Shared utilities."""

from pathlib import Path


def get_project_cache_dir(project_path: Path | None = None) -> Path:
    """
    Get the Claude Code cache directory for a project path.

    Claude Code stores conversation caches in ~/.claude/projects/<path-with-dashes>/
    where the path has slashes replaced by dashes.
    """
    if project_path is None:
        project_path = Path.cwd()

    path_str = str(project_path.resolve())
    cache_name = path_str.replace("/", "-")
    return Path.home() / ".claude" / "projects" / cache_name


def read_file(path: Path) -> str:
    """Read file content, return empty string if not found."""
    if path.exists():
        return path.read_text()
    return ""


def write_file(path: Path, content: str) -> None:
    """Write content to file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
