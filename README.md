# Dynamic Skills

Learn from Claude Code conversations by automatically distilling knowledge into skill files.

## Overview

- **Skill Manager Agent**: Monitors conversations, decides which skills are relevant, spawns/stops observers
- **Skill Observers**: Watch conversations and distill learnings into hierarchical skill files

## Installation

```bash
uv tool install .
```

Or run directly:
```bash
uv run skills-agent
```

## Usage

### Run the Agent

From your project directory:
```bash
skills-agent
```

The agent will:
1. Watch Claude Code conversation cache for your project
2. Evaluate which skills are relevant based on conversation content
3. Spawn observers for relevant skills
4. Create new skills when topics don't match existing ones

### Run an Observer Directly

```bash
skills-observer my-skill --project /path/to/project --description "Description of skill"
```

Options:
- `--project, -p`: Project path to watch (required)
- `--description, -d`: Skill description
- `--include-history`: Process existing conversation history
- `--config, -c`: Path to config file
- `--verbose, -v`: Enable verbose logging

## Skill Structure

Each skill is a directory:
```
skills/
  my-skill/
    index.md      # Compact summary (~4KB) for relevance checking
    details.md    # Full knowledge content (~32KB)
    examples.md   # Optional resource files
    reference.md
```

## Configuration

Create `config.yaml`:
```yaml
skills_dir: skills
max_skill_size: 32768      # details.md max size
max_index_size: 4096       # index.md max size
message_threshold: 5       # messages before distillation
poll_interval: 10          # seconds between polls
agent_message_threshold: 5
agent_poll_interval: 30
```

## How It Works

1. Agent reads Claude Code conversation cache (`~/.claude/projects/<project>/`)
2. After N messages, evaluates skill relevance using Claude
3. Spawns observers for relevant skills as background processes
4. Observers distill conversation into skill files
5. Index updated every 3 distillations for quick relevance checks
# dynamic-skills
