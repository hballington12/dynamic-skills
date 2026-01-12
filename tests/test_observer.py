"""Tests for observer parsing."""

import pytest

from dynamic_skills.observer import DistillResult, parse_distill_response


class TestParseDistillResponse:
    """Tests for parse_distill_response."""

    def test_no_update(self):
        result = parse_distill_response("NO_UPDATE")
        assert result.details is None
        assert result.resource_files is None

    def test_empty_response(self):
        result = parse_distill_response("")
        assert result.details is None

    def test_simple_details(self):
        response = """# My Skill

## Overview
Some content here.

## Notes
- Point 1
- Point 2"""

        result = parse_distill_response(response)
        assert result.details is not None
        assert "# My Skill" in result.details
        assert "Point 2" in result.details
        assert result.resource_files is None

    def test_with_resource_file(self):
        response = """# Main Details

Some content.

NEW_FILE: examples.md
# Examples

Example 1: foo
Example 2: bar"""

        result = parse_distill_response(response)
        assert result.details == "# Main Details\n\nSome content."
        assert result.resource_files is not None
        assert "examples.md" in result.resource_files
        assert "Example 1: foo" in result.resource_files["examples.md"]

    def test_multiple_resource_files(self):
        response = """# Main

Content.

NEW_FILE: examples.md
Example content

NEW_FILE: deprecated.md
Old stuff"""

        result = parse_distill_response(response)
        assert result.details == "# Main\n\nContent."
        assert len(result.resource_files) == 2
        assert "examples.md" in result.resource_files
        assert "deprecated.md" in result.resource_files
        assert "Example content" in result.resource_files["examples.md"]
        assert "Old stuff" in result.resource_files["deprecated.md"]

    def test_only_resource_file(self):
        response = """NEW_FILE: overflow.md
All content goes here"""

        result = parse_distill_response(response)
        assert result.details is None or result.details == ""
        assert result.resource_files is not None
        assert "overflow.md" in result.resource_files
