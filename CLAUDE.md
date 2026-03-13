# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A text-based D&D adventure game powered by a local LLM via [Ollama](https://ollama.com/). An AI Dungeon Master narrates the story; players explore, fight, and cast spells alongside AI-driven NPC companions. Game state is persisted in a local SQLite database (`dnd_game.db`).

## Environment Setup

Copy `.env.example` to `.env` and configure:
```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:32b
```
Both variables are required — the `DungeonMaster` and `NPCAgent` classes raise `ValueError` at instantiation if either is missing.

## Commands

**Run the game:**
```bash
python3 main.py
```

**Run all tests:**
```bash
PYTHONPATH=. pytest
```

**Run a single test file or test:**
```bash
PYTHONPATH=. pytest tests/test_character.py
PYTHONPATH=. pytest tests/test_character.py::test_barbarian_rage
```

## Architecture

### Data Flow

```
main.py
  └── CommandHandler (dnd/cli/__init__.py)
        ├── Player input → /commands handled locally
        └── Free-form input → DungeonMaster.generate_response()
                                └── Streams from Ollama /api/generate
  └── NPCAgent (dnd/npc/agent.py)
        └── "ask <npc> <message>" → Streams from Ollama /api/generate
```

### Key Components

**`CharacterSheet` (`dnd/character.py`)** — The central data model. Every property (HP, stats, inventory, spells, conditions) reads directly from SQLite via `get_db_connection()`. A `refresh_cache()` call must be made after mutations to sync in-memory caches (`_proficiencies_cache`, `_inventory_cache`, `_spells_cache`, `_conditions_cache`). Character stats, class, and level are always fetched live from the DB; only the four caches are stored in memory.

**`CommandHandler` (`dnd/cli/__init__.py`)** — Handles all `/command` and `ask <npc>` inputs. Returns `(skip_dm: bool, forwarded_input: str)`. When `skip_dm=False`, the returned string is sent to the DM as the player action (e.g., after `/cast` or `/equip`). When `skip_dm=True`, the main loop continues without DM narration.

**`DungeonMaster` (`dnd/dm/agent.py`)** — Maintains a `history` list (shared with `NPCAgent.generate_response`) and a `world_state` dict. Builds a full prompt combining the player's character summary, companion list, world state, and conversation history, then streams from Ollama. Parses XML-like tags in the response: `<level_up />` and `<award_gold amount="N" />` trigger game state mutations in `main.py`.

**`NPCAgent` (`dnd/npc/agent.py`)** — One instance per companion. Receives the DM's full `history` as context so the NPC is aware of the ongoing story.

**Database (`dnd/database.py`)** — SQLite with `sqlite3.Row` factory (column access by name). The `DB_FILE` path is `"dnd_game.db"` (repo root). Tests monkeypatch this to a `tmp_path` file. Schema: `characters`, `inventory`, `proficiencies`, `character_proficiencies`, `spells`, `character_spells`, `conditions`.

**Static data (`dnd/data.py`)** — All game constants: `WEAPON_DATA`, `ARMOR_DATA`, `SPELL_DATA`, `CLASS_DATA`, `SKILL_TO_ABILITY_MAP`, `STORE_INVENTORY`. Class starting equipment, stats, spells, and spell slots are defined here and consumed by `character_creator.py` and `character.py`.

### Game Startup Sequence

1. Check for existing `dnd_game.db`; offer to continue or start fresh
2. If new game: `initialize_database()` → `seed_spells()` → `run_character_creation()` → `seed_npcs()`
3. Load player `CharacterSheet` and 2 random NPC companions from DB
4. Create `CommandHandler` wrapping player sheet, all character sheets, NPCs, and the DM
5. Main loop: read input → route to `CommandHandler` or `DungeonMaster`

### Testing Patterns

Tests use `monkeypatch` to redirect `dnd.database.DB_FILE` to a `tmp_path` SQLite file and run `run_character_creation()` with a mocked `input()` iterator. The character creation input sequence must exactly match the prompts (name, class index, background index, stat-boost method, ability choice(s), empty string to finish).

The `CommandHandler` tests use `MagicMock` for all dependencies and do not touch the database.
