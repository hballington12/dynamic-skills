"""Tests for conversation tracking."""

import json
import tempfile
from pathlib import Path

import pytest

from dynamic_skills.tracker import (
    ConversationTracker,
    find_conversation_files,
    parse_jsonl_entry,
    read_messages_from_position,
)


class TestParseJsonlEntry:
    """Tests for parse_jsonl_entry."""

    def test_user_message_simple(self):
        entry = {
            "type": "user",
            "message": {"role": "user", "content": "Hello"},
        }
        result = parse_jsonl_entry(entry)
        assert result == {"role": "user", "content": "Hello"}

    def test_assistant_message_simple(self):
        entry = {
            "type": "assistant",
            "message": {"role": "assistant", "content": "Hi there"},
        }
        result = parse_jsonl_entry(entry)
        assert result == {"role": "assistant", "content": "Hi there"}

    def test_content_blocks(self):
        entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "First part"},
                    {"type": "tool_use", "name": "read"},
                    {"type": "text", "text": "Second part"},
                ],
            },
        }
        result = parse_jsonl_entry(entry)
        assert result == {"role": "assistant", "content": "First part\nSecond part"}

    def test_non_message_entry(self):
        entry = {"type": "system", "data": "something"}
        result = parse_jsonl_entry(entry)
        assert result is None

    def test_empty_content(self):
        entry = {
            "type": "user",
            "message": {"role": "user", "content": ""},
        }
        result = parse_jsonl_entry(entry)
        assert result is None


class TestFindConversationFiles:
    """Tests for find_conversation_files."""

    def test_finds_jsonl_files(self, tmp_path):
        (tmp_path / "conv1.jsonl").write_text("{}")
        (tmp_path / "conv2.jsonl").write_text("{}")
        (tmp_path / "other.txt").write_text("not a conversation")

        files = find_conversation_files(tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".jsonl" for f in files)

    def test_excludes_agent_files(self, tmp_path):
        (tmp_path / "conv1.jsonl").write_text("{}")
        (tmp_path / "agent-123.jsonl").write_text("{}")

        files = find_conversation_files(tmp_path)
        assert len(files) == 1
        assert files[0].name == "conv1.jsonl"

    def test_nonexistent_dir(self, tmp_path):
        files = find_conversation_files(tmp_path / "nonexistent")
        assert files == []


class TestReadMessagesFromPosition:
    """Tests for read_messages_from_position."""

    def test_reads_from_start(self, tmp_path):
        conv_file = tmp_path / "conv.jsonl"
        entries = [
            {"type": "user", "message": {"role": "user", "content": "Hello"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "Hi"}},
        ]
        conv_file.write_text("\n".join(json.dumps(e) for e in entries))

        messages, pos = read_messages_from_position(conv_file, 0)
        assert len(messages) == 2
        assert messages[0]["content"] == "Hello"
        assert messages[1]["content"] == "Hi"
        assert pos > 0

    def test_reads_from_position(self, tmp_path):
        conv_file = tmp_path / "conv.jsonl"
        entry1 = {"type": "user", "message": {"role": "user", "content": "First"}}
        entry2 = {"type": "user", "message": {"role": "user", "content": "Second"}}

        line1 = json.dumps(entry1) + "\n"
        line2 = json.dumps(entry2) + "\n"
        conv_file.write_text(line1 + line2)

        # Read from after first line
        messages, pos = read_messages_from_position(conv_file, len(line1))
        assert len(messages) == 1
        assert messages[0]["content"] == "Second"

    def test_handles_missing_file(self, tmp_path):
        messages, pos = read_messages_from_position(tmp_path / "missing.jsonl", 0)
        assert messages == []
        assert pos == 0


class TestConversationTracker:
    """Tests for ConversationTracker."""

    def test_skip_existing(self, tmp_path):
        conv_file = tmp_path / "conv.jsonl"
        entry = {"type": "user", "message": {"role": "user", "content": "Old message"}}
        conv_file.write_text(json.dumps(entry) + "\n")

        tracker = ConversationTracker(skip_existing=True)
        messages = tracker.update(tmp_path)

        # Should skip existing messages on first run
        assert messages == []

    def test_include_existing(self, tmp_path):
        conv_file = tmp_path / "conv.jsonl"
        entry = {"type": "user", "message": {"role": "user", "content": "Old message"}}
        conv_file.write_text(json.dumps(entry) + "\n")

        tracker = ConversationTracker(skip_existing=False)
        messages = tracker.update(tmp_path)

        # Should include existing messages
        assert len(messages) == 1
        assert messages[0]["content"] == "Old message"

    def test_tracks_new_messages(self, tmp_path):
        conv_file = tmp_path / "conv.jsonl"
        entry1 = {"type": "user", "message": {"role": "user", "content": "First"}}
        conv_file.write_text(json.dumps(entry1) + "\n")

        tracker = ConversationTracker(skip_existing=True)
        tracker.update(tmp_path)  # Skip existing

        # Add new message
        entry2 = {"type": "user", "message": {"role": "user", "content": "Second"}}
        with open(conv_file, "a") as f:
            f.write(json.dumps(entry2) + "\n")

        messages = tracker.update(tmp_path)
        assert len(messages) == 1
        assert messages[0]["content"] == "Second"
