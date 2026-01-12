"""Configuration management with validation."""

import logging
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Config(BaseModel):
    """Configuration for dynamic skills."""

    # Skills directory (relative to project or absolute)
    skills_dir: Path = Field(default=Path("skills"))

    # Maximum details.md size in bytes
    max_skill_size: int = Field(default=32768, ge=1024)

    # Maximum index.md size in bytes
    max_index_size: int = Field(default=4096, ge=256)

    # Observer settings
    message_threshold: int = Field(default=5, ge=1)
    poll_interval: int = Field(default=10, ge=1)

    # Agent settings
    agent_message_threshold: int = Field(default=5, ge=1)
    agent_poll_interval: int = Field(default=30, ge=1)

    @classmethod
    def load(cls, path: Path | str | None = None) -> Self:
        """Load config from YAML file, with defaults for missing values."""
        if path is None:
            return cls()

        path = Path(path)
        if not path.exists():
            logger.warning(f"Config file not found: {path}, using defaults")
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)

    def save(self, path: Path | str) -> None:
        """Save config to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False)
