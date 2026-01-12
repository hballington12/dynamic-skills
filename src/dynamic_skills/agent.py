"""
Skill Manager Agent

Monitors Claude Code conversations and manages skill observers.
Decides which skills are relevant and spawns/stops observers accordingly.
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from claude_code_sdk import query, ClaudeCodeOptions

from .config import Config
from .skill import SkillDir, get_running_observers, list_skills
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


def format_messages_for_prompt(messages: list[dict]) -> str:
    """Format messages for inclusion in a prompt."""
    messages = truncate_messages(messages)
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)


def get_skill_summaries(skills_dir: Path, skill_names: list[str]) -> str:
    """Get index summaries for all skills."""
    summaries = []
    for name in skill_names:
        skill_dir = SkillDir(skills_dir / name)
        index = skill_dir.read_index()
        if index:
            summaries.append(f"### {name}\n{index}")
        else:
            # Check for legacy .md file
            legacy_path = skills_dir / f"{name}.md"
            if legacy_path.exists():
                content = legacy_path.read_text()[:500]
                summaries.append(f"### {name}\n{content}...")

    return "\n\n".join(summaries) if summaries else "(no skill summaries available)"


async def evaluate_skills(
    messages: list[dict],
    existing_skills: list[str],
    running_observers: list[str],
    skills_dir: Path,
) -> dict:
    """
    Evaluate which skills should be started or stopped based on conversation.

    Returns dict with 'start' and 'stop' lists.
    """
    conversation_text = format_messages_for_prompt(messages)
    skill_summaries = get_skill_summaries(skills_dir, existing_skills)

    prompt = f"""You are a skill manager for a Claude Code session.

CURRENT CONVERSATION:
```
{conversation_text}
```

EXISTING SKILLS:
{skill_summaries}

CURRENTLY RUNNING OBSERVERS: {running_observers if running_observers else "(none)"}

Your job is to decide:
1. Which NEW skills should be created based on this conversation topic
2. Which EXISTING skills should have their observers started (if relevant and not running)
3. Which running observers should be STOPPED (if no longer relevant)

GUIDELINES:
- Start observers for skills that match the conversation topic
- Create new skills when the topic doesn't match existing skills
- Stop observers that are clearly no longer relevant
- Be conservative - don't stop skills that might become relevant again
- Skill names should be short, lowercase, hyphenated (e.g., "react-hooks", "postgres-queries")

Respond in this exact format:
START: skill1, skill2 (or "none")
STOP: skill3 (or "none")
NEW: skill-name: description (or "none")
REASON: Brief explanation of your decision"""

    result = None
    options = ClaudeCodeOptions(max_turns=1)

    async for msg in query(prompt=prompt, options=options):
        if hasattr(msg, "content"):
            for block in msg.content:
                if hasattr(block, "text"):
                    result = block.text

    if not result:
        return {"start": [], "stop": [], "new": [], "reason": "No response"}

    return parse_skill_decision(result)


def parse_skill_decision(response: str) -> dict:
    """Parse the skill decision response."""
    result = {"start": [], "stop": [], "new": [], "reason": ""}

    for line in response.strip().split("\n"):
        line = line.strip()
        if line.startswith("START:"):
            skills = line.replace("START:", "").strip()
            if skills.lower() != "none":
                result["start"] = [s.strip() for s in skills.split(",") if s.strip()]
        elif line.startswith("STOP:"):
            skills = line.replace("STOP:", "").strip()
            if skills.lower() != "none":
                result["stop"] = [s.strip() for s in skills.split(",") if s.strip()]
        elif line.startswith("NEW:"):
            new_skill = line.replace("NEW:", "").strip()
            if new_skill.lower() != "none" and ":" in new_skill:
                name, desc = new_skill.split(":", 1)
                result["new"].append({"name": name.strip(), "description": desc.strip()})
        elif line.startswith("REASON:"):
            result["reason"] = line.replace("REASON:", "").strip()

    return result


def start_observer(
    skill_name: str,
    description: str,
    project_path: Path,
    skills_dir: Path,
    config_path: Path | None,
    include_history: bool = False,
) -> int | None:
    """
    Start an observer subprocess for a skill.

    Returns the PID if successful, None otherwise.
    """
    # Create log file path
    log_dir = skills_dir / ".logs"
    log_file = log_dir / f"{skill_name}.log"

    cmd = [
        sys.executable,
        "-m",
        "dynamic_skills.cli",
        "observer",
        skill_name,
        "--description",
        description,
        "--project",
        str(project_path),
        "--log-file",
        str(log_file),
    ]

    if config_path:
        cmd.extend(["--config", str(config_path)])

    if include_history:
        cmd.append("--include-history")

    try:
        # Start detached process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(f"Started observer: {skill_name} (PID {process.pid})")
        logger.info(f"  Log file: {log_file}")
        return process.pid
    except Exception as e:
        logger.error(f"Failed to start observer for {skill_name}: {e}")
        return None


def stop_observer(skill_name: str, pid: int) -> bool:
    """Stop an observer by sending SIGTERM."""
    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"Stopped observer: {skill_name} (PID {pid})")
        return True
    except ProcessLookupError:
        logger.warning(f"Observer {skill_name} (PID {pid}) already stopped")
        return True
    except Exception as e:
        logger.error(f"Failed to stop observer {skill_name}: {e}")
        return False


async def run_agent(
    project_path: Path,
    config: Config,
    config_path: Path | None = None,
) -> None:
    """Run the skill manager agent loop."""
    cache_dir = get_project_cache_dir(project_path)
    skills_dir = config.skills_dir

    # Make skills_dir absolute if relative
    if not skills_dir.is_absolute():
        skills_dir = project_path / skills_dir

    tracker = ConversationTracker(skip_existing=True)
    pending_messages: list[dict] = []

    logger.info("Skill Manager Agent started")
    logger.info(f"  Project: {project_path}")
    logger.info(f"  Cache dir: {cache_dir}")
    logger.info(f"  Skills dir: {skills_dir}")

    # Check for existing conversation
    from .tracker import find_conversation_files

    conv_files = find_conversation_files(cache_dir)
    if conv_files:
        logger.info(f"  Conversation: {conv_files[0].name}")
    else:
        logger.info("  Conversation: (none found)")

    existing_skills = list_skills(skills_dir)
    running = get_running_observers(skills_dir)

    logger.info(f"  Existing skills: {existing_skills}")
    logger.info(f"  Running observers: {list(running.keys())}")

    shutdown_requested = False

    def handle_shutdown(signum=None, frame=None):
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info("Shutdown requested...")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        while not shutdown_requested:
            new_messages = tracker.update(cache_dir)

            if new_messages:
                pending_messages.extend(new_messages)
                logger.debug(
                    f"{len(new_messages)} new messages ({len(pending_messages)} pending)"
                )

            if len(pending_messages) >= config.agent_message_threshold:
                logger.info(
                    f"Evaluating skills based on {len(pending_messages)} messages..."
                )

                existing_skills = list_skills(skills_dir)
                running = get_running_observers(skills_dir)

                decision = await evaluate_skills(
                    pending_messages,
                    existing_skills,
                    list(running.keys()),
                    skills_dir,
                )

                logger.info(f"  Decision: {decision['reason']}")

                # Handle new skills
                for new_skill in decision.get("new", []):
                    name = new_skill["name"]
                    desc = new_skill["description"]
                    if name not in running:
                        pid = start_observer(
                            name, desc, project_path, skills_dir, config_path, include_history=True
                        )
                        if pid:
                            running[name] = pid
                            print(f"Started observer: {name} (PID {pid})")

                # Handle starting existing skills
                for skill_name in decision.get("start", []):
                    if skill_name in running:
                        print(f"Observer already running: {skill_name}")
                    elif skill_name in existing_skills:
                        skill_dir = SkillDir(skills_dir / skill_name)
                        desc = f"Knowledge about {skill_name}"
                        pid = start_observer(
                            skill_name, desc, project_path, skills_dir, config_path
                        )
                        if pid:
                            running[skill_name] = pid
                            print(f"Started observer: {skill_name} (PID {pid})")

                # Handle stopping skills
                for skill_name in decision.get("stop", []):
                    if skill_name in running:
                        stop_observer(skill_name, running[skill_name])
                        del running[skill_name]
                        print(f"Stopped observer: {skill_name}")

                pending_messages.clear()

            await asyncio.sleep(config.agent_poll_interval)

    except asyncio.CancelledError:
        pass
    finally:
        # Gracefully stop all observers on shutdown
        running = get_running_observers(skills_dir)
        for skill_name, pid in running.items():
            stop_observer(skill_name, pid)
        logger.info("Agent stopped")
