"""Command-line interface for dynamic-skills."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import Config


def setup_logging(
    verbose: bool = False,
    log_file: Path | None = None,
) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=handlers,
    )


def agent_main() -> None:
    """Entry point for skills-agent command."""
    parser = argparse.ArgumentParser(
        description="Skill Manager Agent - monitors conversations and manages skill observers"
    )
    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=None,
        help="Project path to watch (default: current directory)",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to config file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)

    # Determine project path
    project_path = args.project or Path.cwd()
    project_path = project_path.resolve()

    # Load config
    config = Config.load(args.config)

    # Import here to avoid circular imports
    from .agent import run_agent

    asyncio.run(run_agent(project_path, config, args.config))


def observer_main() -> None:
    """Entry point for skills-observer command."""
    parser = argparse.ArgumentParser(
        description="Skill Observer - watches conversations and distills learnings into a skill"
    )
    parser.add_argument(
        "skill_name",
        help="Name of the skill to observe",
    )
    parser.add_argument(
        "--description",
        "-d",
        default="General knowledge about this topic",
        help="Description of what this skill covers",
    )
    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        required=True,
        help="Project path to watch",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to config file",
    )
    parser.add_argument(
        "--include-history",
        action="store_true",
        help="Include existing conversation history (don't skip to end)",
    )
    parser.add_argument(
        "--log-file",
        "-l",
        type=Path,
        default=None,
        help="Path to log file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    setup_logging(args.verbose, args.log_file)

    # Load config
    config = Config.load(args.config)

    # Import here to avoid circular imports
    from .observer import run_observer

    asyncio.run(
        run_observer(
            skill_name=args.skill_name,
            skill_description=args.description,
            config=config,
            project_path=args.project.resolve(),
            skip_existing=not args.include_history,
        )
    )


def main() -> None:
    """
    Main entry point that dispatches to agent or observer based on subcommand.

    This allows running as: python -m dynamic_skills agent/observer
    """
    parser = argparse.ArgumentParser(
        description="Dynamic Skills - learn from Claude Code conversations"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Agent subcommand
    agent_parser = subparsers.add_parser(
        "agent",
        help="Run the skill manager agent",
    )
    agent_parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=None,
        help="Project path to watch (default: current directory)",
    )
    agent_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to config file",
    )
    agent_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    # Observer subcommand
    observer_parser = subparsers.add_parser(
        "observer",
        help="Run a skill observer",
    )
    observer_parser.add_argument(
        "skill_name",
        help="Name of the skill to observe",
    )
    observer_parser.add_argument(
        "--description",
        "-d",
        default="General knowledge about this topic",
        help="Description of what this skill covers",
    )
    observer_parser.add_argument(
        "--project",
        "-p",
        type=Path,
        required=True,
        help="Project path to watch",
    )
    observer_parser.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to config file",
    )
    observer_parser.add_argument(
        "--include-history",
        action="store_true",
        help="Include existing conversation history",
    )
    observer_parser.add_argument(
        "--log-file",
        "-l",
        type=Path,
        default=None,
        help="Path to log file",
    )
    observer_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    log_file = getattr(args, "log_file", None)
    setup_logging(args.verbose, log_file)

    if args.command == "agent":
        project_path = (args.project or Path.cwd()).resolve()
        config = Config.load(args.config)

        from .agent import run_agent

        asyncio.run(run_agent(project_path, config, args.config))

    elif args.command == "observer":
        config = Config.load(args.config)

        from .observer import run_observer

        asyncio.run(
            run_observer(
                skill_name=args.skill_name,
                skill_description=args.description,
                config=config,
                project_path=args.project.resolve(),
                skip_existing=not args.include_history,
            )
        )


if __name__ == "__main__":
    main()
