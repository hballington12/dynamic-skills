"""
Skill Observer

Watches Claude Code conversation cache and distills learnings into skill files.
Each observer instance handles one skill.
"""

import asyncio
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path

from claude_code_sdk import query, ClaudeCodeOptions

from .config import Config
from .skill import SkillDir, remove_pid_file, write_pid_file
from .tracker import ConversationTracker
from .utils import get_project_cache_dir

logger = logging.getLogger(__name__)


def truncate_messages(messages: list[dict], max_chars: int = 30000) -> list[dict]:
    """Truncate messages to fit within size limit, keeping most recent."""
    result = []
    total_chars = 0

    for msg in reversed(messages):
        content = msg.get("content", "")
        if len(content) > 2000:
            content = content[:2000] + "..."
            msg = {"role": msg["role"], "content": content}

        msg_chars = len(content)
        if total_chars + msg_chars > max_chars:
            break
        result.append(msg)
        total_chars += msg_chars

    return list(reversed(result))


@dataclass
class DistillResult:
    """Result of a distillation operation."""

    details: str | None = None
    resource_files: dict[str, str] | None = None  # filename -> content


def parse_distill_response(response: str) -> DistillResult:
    """Parse the distillation response, extracting details and any resource files."""
    if not response or response.strip() == "NO_UPDATE":
        return DistillResult()

    # Look for NEW_FILE: markers
    resource_files = {}
    lines = response.split("\n")
    main_content_lines = []
    current_file = None
    current_file_lines = []

    for line in lines:
        if line.startswith("NEW_FILE:"):
            # Save previous file if any
            if current_file:
                resource_files[current_file] = "\n".join(current_file_lines).strip()
            current_file = line.replace("NEW_FILE:", "").strip()
            current_file_lines = []
        elif current_file:
            current_file_lines.append(line)
        else:
            main_content_lines.append(line)

    # Save last file if any
    if current_file:
        resource_files[current_file] = "\n".join(current_file_lines).strip()

    details = "\n".join(main_content_lines).strip()

    return DistillResult(
        details=details if details else None,
        resource_files=resource_files if resource_files else None,
    )


async def distill_details(
    skill_name: str,
    skill_description: str,
    recent_messages: list[dict],
    current_details: str,
    existing_resources: list[str],
    max_size: int,
) -> DistillResult:
    """Distill learnings into details.md and optional resource files."""
    messages = truncate_messages(recent_messages)

    conversation_text = ""
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        conversation_text += f"[{role}]: {content}\n\n"

    resources_note = ""
    if existing_resources:
        resources_note = f"\nEXISTING RESOURCE FILES: {', '.join(existing_resources)}"

    prompt = f"""You are a knowledge distiller for the skill: "{skill_name}"
Skill description: {skill_description}

Your job is to maintain a comprehensive knowledge file capturing relevant learnings.

CURRENT DETAILS FILE:
```
{current_details if current_details else "(empty)"}
```
{resources_note}

RECENT CONVERSATION:
```
{conversation_text}
```

GUIDELINES:
- Capture everything relevant to "{skill_name}"
- Include: patterns, examples, gotchas, user corrections, code snippets
- Organize with clear markdown sections
- Prioritize: user corrections > patterns > preferences > facts
- Maximum size: {max_size} bytes
- Remove outdated info as necessary
- If space is needed, make an informed decision on whether to merge, replace, swap, or discard incoming info with existing info
- You may create additional resource files (e.g., examples.md, deprecated.md, reference.md) for less important information

OUTPUT FORMAT:
- If updates needed: output the complete updated details.md content
- To create resource files, append after the main content:
  NEW_FILE: filename.md
  (file content here)
- If nothing to add: respond with exactly: NO_UPDATE"""

    logger.debug(f"Calling Claude for distillation ({len(conversation_text)} chars of conversation)")
    result = None
    options = ClaudeCodeOptions(max_turns=1)

    async for msg in query(prompt=prompt, options=options):
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    result = block.text

    if not result:
        logger.debug("No response from distillation call")
        return DistillResult()

    logger.debug(f"Distillation response: {len(result)} chars")
    return parse_distill_response(result.strip())


async def summarize_index(
    skill_name: str,
    skill_description: str,
    details_content: str,
    max_index_size: int,
) -> str | None:
    """Summarize details.md into a compact index.md."""
    prompt = f"""You are summarizing a skill's detailed knowledge into a compact index.

SKILL: {skill_name}
DESCRIPTION: {skill_description}

FULL DETAILS:
```
{details_content}
```

Create a concise index.md (under {max_index_size} bytes) that is as information-dense as possible.

GUIDELINES:
- Retain the most important information and as much detail as space allows
- One-paragraph overview
- Key facts/constraints (bullet points)
- Most important gotchas
- Quick reference (common commands/patterns)
- Use terse language, abbreviations where clear, and compact formatting

This index helps decide IF this skill is relevant. Full details are loaded separately when needed.

OUTPUT: The complete index.md content (no explanation, no code fences)"""

    logger.debug("Calling Claude for index summarization")
    result = None
    options = ClaudeCodeOptions(max_turns=1)

    async for msg in query(prompt=prompt, options=options):
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    result = block.text

    if not result:
        logger.debug("No response from index summarization call")
        return None

    result = result.strip()
    logger.debug(f"Index summarization response: {len(result)} chars")

    # Enforce size limit
    if len(result.encode("utf-8")) > max_index_size:
        result = result.encode("utf-8")[:max_index_size].decode("utf-8", errors="ignore")

    return result


async def run_observer(
    skill_name: str,
    skill_description: str,
    config: Config,
    project_path: Path,
    skip_existing: bool = True,
) -> None:
    """Run the observer loop for a specific skill."""
    cache_dir = get_project_cache_dir(project_path)
    skills_dir = config.skills_dir

    # Make skills_dir absolute if relative
    if not skills_dir.is_absolute():
        skills_dir = project_path / skills_dir

    skill_dir = SkillDir(skills_dir / skill_name)

    tracker = ConversationTracker(skip_existing=skip_existing)
    pending_messages: list[dict] = []
    distill_count = 0

    logger.info(f"Skill Observer started: {skill_name}")
    logger.info(f"  Description: {skill_description}")
    logger.info(f"  Skill dir: {skill_dir.base_dir}")
    logger.info(f"  Include history: {not skip_existing}")

    # Write PID file for management
    write_pid_file(skills_dir, skill_name, os.getpid())

    shutdown_requested = False

    def handle_shutdown(signum=None, frame=None):
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info(f"[{skill_name}] Shutdown requested, finishing current work...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    poll_count = 0
    try:
        while not shutdown_requested:
            poll_count += 1
            logger.debug(f"[{skill_name}] Poll #{poll_count}")

            new_messages = tracker.update(cache_dir)

            if new_messages:
                pending_messages.extend(new_messages)
                logger.info(
                    f"[{skill_name}] {len(new_messages)} new messages "
                    f"({len(pending_messages)} pending)"
                )
            else:
                logger.debug(f"[{skill_name}] No new messages")

            # Distill if threshold reached OR if shutting down with pending messages
            should_distill = len(pending_messages) >= config.message_threshold
            if shutdown_requested and pending_messages:
                should_distill = True
                logger.info(f"[{skill_name}] Final distillation before shutdown...")

            if should_distill and pending_messages:
                logger.info(f"[{skill_name}] Distilling {len(pending_messages)} messages...")

                current_details = skill_dir.read_details()
                existing_resources = skill_dir.list_resources()

                result = await distill_details(
                    skill_name,
                    skill_description,
                    pending_messages,
                    current_details,
                    existing_resources,
                    config.max_skill_size,
                )

                if result.details:
                    skill_dir.write_details(result.details)
                    logger.info(
                        f"[{skill_name}] Updated details.md ({len(result.details)} bytes)"
                    )
                    distill_count += 1

                    # Write any resource files
                    if result.resource_files:
                        for filename, content in result.resource_files.items():
                            skill_dir.write_resource(filename, content)
                            logger.info(
                                f"[{skill_name}] Created {filename} ({len(content)} bytes)"
                            )

                    # Update index periodically (every 3 distillations or on shutdown)
                    if distill_count % 3 == 0 or shutdown_requested:
                        logger.info(f"[{skill_name}] Updating index.md...")
                        index_content = await summarize_index(
                            skill_name,
                            skill_description,
                            result.details,
                            config.max_index_size,
                        )
                        if index_content:
                            skill_dir.write_index(index_content)
                            logger.info(
                                f"[{skill_name}] Updated index.md ({len(index_content)} bytes)"
                            )
                else:
                    logger.info(f"[{skill_name}] No relevant updates")

                pending_messages.clear()

            if shutdown_requested:
                break

            await asyncio.sleep(config.poll_interval)

    except asyncio.CancelledError:
        pass
    finally:
        remove_pid_file(skills_dir, skill_name)
        logger.info(f"[{skill_name}] Observer stopped")
