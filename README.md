# D&D Text Adventure

A text-based D&D learning game powered by a local Ollama model. You create a character, pick `0-5` AI companions, explore alone or with a party through free-form prompts, and use built-in commands for rules help, transparent combat math, and encounter tracking.

## Features

- AI Dungeon Master for narration and scene responses
- AI-generated opening scene tailored to the player and companions
- Character creation with class, background, and stat choices
- Optional companion party from `0` to `5` NPCs
- Teaching mode with rules-aware attack and spell breakdowns
- Guided suggested actions for new players
- `/help`, `/rules`, `/journal`, and `/map` for in-game reference
- Encounter-scoped initiative with player, companion, and enemy turns
- file-based save slots under `saves/` plus session-scoped world/NPC memory

## Requirements

- Python `3.13+`
- One of:
  - [Ollama](https://ollama.com/) running locally with a model (e.g. `qwen2.5`)
  - The [Claude CLI](https://claude.ai/code) (`claude`) on your `PATH`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Ollama backend** (default): set `OLLAMA_HOST` and `OLLAMA_MODEL` in `.env`.

**Claude CLI backend**: set `USE_CLAUDE_CLI=true` in `.env`. Ollama vars are not required. Optionally set `CLAUDE_CLI_MODEL` to choose a model (default: `claude-sonnet-4-6`):

```env
USE_CLAUDE_CLI=true
CLAUDE_CLI_MODEL=claude-haiku-4-5
```

Then start the game:

```bash
python3 main.py
```

At startup, you can pick an existing save, create a named save, or delete a save file entirely. If you leave the name blank, the game creates a timestamped save name automatically.

## Core Commands

- `/teach on` toggles rules explanations.
- `/attack <weapon>` shows to-hit and damage math.
- `/cast <spell>` shows spell math and then casts.
- `/help <topic>` and `/rules <topic>` show quick references.
- `/journal`, `/map`, and `/inventory` review current state.
- `ask <npc> <message>` talks directly to a companion.

## Encounter Commands

- `/encounter start Goblin, Orc:1` starts initiative and optionally sets enemy initiative modifiers.
- `/turn` shows the active actor and current order.
- `/npcturn` runs the active companion turn.
- `/enemyturn` prompts the DM for the active enemy turn.
- `/endturn` advances to the next actor.
- `/encounter end` exits combat mode.

## Testing

Run the full test suite with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q
```

Current project coverage is command handling, character logic, NPC behavior, and database-backed gameplay helpers.
