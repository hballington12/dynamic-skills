"""Tests for skill management."""

import os
from pathlib import Path

import pytest

from dynamic_skills.skill import (
    SkillDir,
    get_running_observers,
    list_skills,
    remove_pid_file,
    write_pid_file,
)


class TestSkillDir:
    """Tests for SkillDir."""

    def test_paths(self, tmp_path):
        skill_dir = SkillDir(tmp_path / "my-skill")

        assert skill_dir.index_path == tmp_path / "my-skill" / "index.md"
        assert skill_dir.details_path == tmp_path / "my-skill" / "details.md"
        assert skill_dir.resource_path("examples.md") == tmp_path / "my-skill" / "examples.md"

    def test_exists(self, tmp_path):
        skill_dir = SkillDir(tmp_path / "my-skill")
        assert not skill_dir.exists()

        skill_dir.base_dir.mkdir()
        assert skill_dir.exists()

    def test_read_write_index(self, tmp_path):
        skill_dir = SkillDir(tmp_path / "my-skill")

        # Read non-existent returns empty
        assert skill_dir.read_index() == ""

        # Write creates directory and file
        skill_dir.write_index("# Index")
        assert skill_dir.read_index() == "# Index"

    def test_read_write_details(self, tmp_path):
        skill_dir = SkillDir(tmp_path / "my-skill")

        assert skill_dir.read_details() == ""
        skill_dir.write_details("# Details")
        assert skill_dir.read_details() == "# Details"

    def test_list_resources(self, tmp_path):
        skill_dir = SkillDir(tmp_path / "my-skill")
        skill_dir.base_dir.mkdir(parents=True)

        # Create files
        (skill_dir.base_dir / "index.md").write_text("index")
        (skill_dir.base_dir / "details.md").write_text("details")
        (skill_dir.base_dir / "examples.md").write_text("examples")
        (skill_dir.base_dir / "reference.md").write_text("reference")

        resources = skill_dir.list_resources()
        assert "examples.md" in resources
        assert "reference.md" in resources
        assert "index.md" not in resources
        assert "details.md" not in resources


class TestListSkills:
    """Tests for list_skills."""

    def test_empty_dir(self, tmp_path):
        assert list_skills(tmp_path) == []

    def test_nonexistent_dir(self, tmp_path):
        assert list_skills(tmp_path / "nonexistent") == []

    def test_directory_skills(self, tmp_path):
        # New-style directory skills
        (tmp_path / "react-hooks").mkdir()
        (tmp_path / "react-hooks" / "index.md").write_text("index")

        (tmp_path / "postgres").mkdir()
        (tmp_path / "postgres" / "details.md").write_text("details")

        skills = list_skills(tmp_path)
        assert "react-hooks" in skills
        assert "postgres" in skills

    def test_legacy_md_files(self, tmp_path):
        (tmp_path / "old-skill.md").write_text("content")

        skills = list_skills(tmp_path)
        assert "old-skill" in skills

    def test_ignores_hidden_dirs(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "index.md").write_text("index")

        skills = list_skills(tmp_path)
        assert ".hidden" not in skills


class TestPidFiles:
    """Tests for PID file management."""

    def test_write_and_remove_pid_file(self, tmp_path):
        write_pid_file(tmp_path, "my-skill", 12345)

        pid_file = tmp_path / ".my-skill.pid"
        assert pid_file.exists()
        assert pid_file.read_text() == "12345"

        remove_pid_file(tmp_path, "my-skill")
        assert not pid_file.exists()

    def test_remove_nonexistent_pid_file(self, tmp_path):
        # Should not raise
        remove_pid_file(tmp_path, "nonexistent")

    def test_get_running_observers_current_process(self, tmp_path):
        # Write PID file for current process (guaranteed to exist)
        current_pid = os.getpid()
        write_pid_file(tmp_path, "active-skill", current_pid)

        running = get_running_observers(tmp_path)
        assert "active-skill" in running
        assert running["active-skill"] == current_pid

    def test_get_running_observers_stale_pid(self, tmp_path):
        # Write PID file for non-existent process
        (tmp_path / ".stale-skill.pid").write_text("999999999")

        running = get_running_observers(tmp_path)
        assert "stale-skill" not in running

        # Stale file should be cleaned up
        assert not (tmp_path / ".stale-skill.pid").exists()
