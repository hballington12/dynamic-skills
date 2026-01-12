"""Skill directory management."""

from dataclasses import dataclass
from pathlib import Path

from .utils import read_file, write_file


@dataclass
class SkillDir:
    """
    Manages a skill's directory structure.

    Each skill has:
    - index.md: Compact summary for relevance checking
    - details.md: Full knowledge content
    - *.md: Optional resource files for overflow content
    """

    base_dir: Path

    @property
    def index_path(self) -> Path:
        return self.base_dir / "index.md"

    @property
    def details_path(self) -> Path:
        return self.base_dir / "details.md"

    def resource_path(self, name: str) -> Path:
        return self.base_dir / name

    def exists(self) -> bool:
        """Check if the skill directory exists."""
        return self.base_dir.exists()

    def read_index(self) -> str:
        return read_file(self.index_path)

    def read_details(self) -> str:
        return read_file(self.details_path)

    def write_index(self, content: str) -> None:
        write_file(self.index_path, content)

    def write_details(self, content: str) -> None:
        write_file(self.details_path, content)

    def write_resource(self, name: str, content: str) -> None:
        write_file(self.resource_path(name), content)

    def list_resources(self) -> list[str]:
        """List all resource files (excluding index.md and details.md)."""
        if not self.base_dir.exists():
            return []
        return [
            f.name
            for f in self.base_dir.glob("*.md")
            if f.name not in ("index.md", "details.md")
        ]


def list_skills(skills_dir: Path) -> list[str]:
    """
    List all available skills.

    Handles both new directory structure (skill_name/) and legacy .md files.
    """
    if not skills_dir.exists():
        return []

    skills = set()

    # New structure: directories with index.md or details.md
    for d in skills_dir.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            if (d / "index.md").exists() or (d / "details.md").exists():
                skills.add(d.name)

    # Legacy: standalone .md files
    for f in skills_dir.glob("*.md"):
        skills.add(f.stem)

    return sorted(skills)


def get_running_observers(skills_dir: Path) -> dict[str, int]:
    """
    Get currently running observers from PID files.

    Returns dict of skill_name -> pid for observers that are still running.
    """
    import os
    import signal

    if not skills_dir.exists():
        return {}

    running = {}
    for pid_file in skills_dir.glob(".*.pid"):
        skill_name = pid_file.stem[1:]  # Remove leading dot
        try:
            pid = int(pid_file.read_text().strip())
            # Check if process is still running
            os.kill(pid, 0)
            running[skill_name] = pid
        except (ValueError, ProcessLookupError, PermissionError):
            # Invalid PID or process not running - clean up stale file
            pid_file.unlink(missing_ok=True)

    return running


def write_pid_file(skills_dir: Path, skill_name: str, pid: int) -> Path:
    """Write a PID file for an observer."""
    pid_file = skills_dir / f".{skill_name}.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid))
    return pid_file


def remove_pid_file(skills_dir: Path, skill_name: str) -> None:
    """Remove a PID file for an observer."""
    pid_file = skills_dir / f".{skill_name}.pid"
    pid_file.unlink(missing_ok=True)
