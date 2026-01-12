"""Conversation tracking for Claude Code cache files."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_conversation_files(cache_dir: Path) -> list[Path]:
    """
    Find all conversation JSONL files in the cache directory.

    Returns files sorted by modification time (most recent first).
    Excludes agent-* files which are SDK sub-conversations.
    """
    if not cache_dir.exists():
        return []

    files = []
    for f in cache_dir.rglob("*.jsonl"):
        # Skip agent sub-conversations created by SDK calls
        if f.stem.startswith("agent-"):
            continue
        files.append(f)

    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def parse_jsonl_entry(entry: dict) -> dict | None:
    """
    Parse a JSONL entry from Claude Code's conversation cache.

    Returns a normalized message dict with role and content, or None if not a message.
    """
    entry_type = entry.get("type")
    if entry_type not in ("user", "assistant"):
        return None

    message = entry.get("message", {})
    role = message.get("role", entry_type)
    content = message.get("content", "")

    # Handle content blocks (list of text/tool_use/etc)
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        content = "\n".join(text_parts)

    if not content:
        return None

    return {"role": role, "content": content}


def read_messages_from_position(
    conv_file: Path, last_position: int = 0
) -> tuple[list[dict], int]:
    """
    Read messages from a conversation file starting from last_position.

    Returns (messages, new_position).
    """
    messages = []
    try:
        with open(conv_file) as f:
            f.seek(last_position)
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        parsed = parse_jsonl_entry(entry)
                        if parsed:
                            messages.append(parsed)
                    except json.JSONDecodeError:
                        continue
            new_position = f.tell()
    except (FileNotFoundError, PermissionError) as e:
        logger.warning(f"Could not read {conv_file}: {e}")
        return [], last_position

    return messages, new_position


class ConversationTracker:
    """
    Tracks the most recent conversation file and its read position.

    Handles file switching when a new conversation starts.
    """

    def __init__(self, skip_existing: bool = True):
        """
        Initialize tracker.

        Args:
            skip_existing: If True, skip to end of file on first run
                          (don't process historical messages).
        """
        self.file_position: int = 0
        self.current_file: str | None = None
        self.skip_existing = skip_existing
        self.initialized = False

    def update(self, cache_dir: Path) -> list[dict]:
        """
        Check for new messages in the most recent conversation.

        Returns list of new messages since last call.
        """
        conv_files = find_conversation_files(cache_dir)
        if not conv_files:
            return []

        most_recent = conv_files[0]
        file_key = str(most_recent)

        # If we switched to a new conversation, reset position
        if file_key != self.current_file:
            self.current_file = file_key
            if self.skip_existing and not self.initialized:
                # Skip to end of file on first run
                self.file_position = most_recent.stat().st_size
                self.initialized = True
                logger.debug(f"Skipping existing messages in {most_recent.name}")
                return []
            else:
                self.file_position = 0
                logger.info(f"Tracking new conversation: {most_recent.name}")

        messages, new_pos = read_messages_from_position(most_recent, self.file_position)
        self.file_position = new_pos
        self.initialized = True

        return messages
