"""Tests for configuration."""

from pathlib import Path

import pytest

from dynamic_skills.config import Config


class TestConfig:
    """Tests for Config."""

    def test_defaults(self):
        config = Config()

        assert config.skills_dir == Path("skills")
        assert config.max_skill_size == 32768
        assert config.max_index_size == 4096
        assert config.message_threshold == 5
        assert config.poll_interval == 10
        assert config.agent_message_threshold == 5
        assert config.agent_poll_interval == 30

    def test_load_nonexistent_file(self, tmp_path):
        config = Config.load(tmp_path / "nonexistent.yaml")
        # Should return defaults
        assert config.skills_dir == Path("skills")

    def test_load_from_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
skills_dir: custom_skills
max_skill_size: 65536
message_threshold: 10
""")

        config = Config.load(config_file)
        assert config.skills_dir == Path("custom_skills")
        assert config.max_skill_size == 65536
        assert config.message_threshold == 10
        # Unspecified values use defaults
        assert config.max_index_size == 4096

    def test_load_empty_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        config = Config.load(config_file)
        assert config.skills_dir == Path("skills")

    def test_save_and_load(self, tmp_path):
        config = Config(
            skills_dir=Path("my_skills"),
            max_skill_size=50000,
        )

        config_file = tmp_path / "config.yaml"
        config.save(config_file)

        loaded = Config.load(config_file)
        assert loaded.skills_dir == Path("my_skills")
        assert loaded.max_skill_size == 50000

    def test_validation_min_values(self):
        # Should raise validation error for values below minimum
        with pytest.raises(ValueError):
            Config(max_skill_size=100)  # Minimum is 1024

        with pytest.raises(ValueError):
            Config(message_threshold=0)  # Minimum is 1
