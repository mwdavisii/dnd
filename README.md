# D&D Text Adventure

A text-based D&D game powered by a local LLM (via Ollama). An AI Dungeon Master narrates the story while you explore, fight, and cast spells alongside NPC companions.

## Features

- **AI Dungeon Master** - Dynamic storytelling powered by Ollama
- **Character Creation** - Build your character with stats, class, and equipment
- **NPC Companions** - AI-driven party members you can talk to
- **Combat System** - Attack rolls, damage, and spell casting with slot management
- **Dice Rolling** - Standard D&D dice notation (`/roll 2d6+3`)
- **Persistent Saves** - SQLite database saves your game state

## Requirements

- Python 3.13+
- [Ollama](https://ollama.com/) running locally

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure Ollama connection (defaults shown)
cp .env.example .env
# Edit .env to set OLLAMA_HOST and OLLAMA_MODEL
```

## Usage

```bash
python main.py
```

### In-Game Commands

| Command | Description |
|---|---|
| `/roll <dice>` | Roll dice (e.g. `/roll 1d20+5`) |
| `/sheet` | View your character sheet |
| `/attack <weapon>` | Attack with a weapon in your inventory |
| `/cast <spell>` | Cast a known spell |
| `ask <npc> <message>` | Talk to an NPC companion |
| `quit` | Save and exit |

Anything else you type is sent to the Dungeon Master as a free-form action.

## Testing

```bash
pytest
```

## Project Structure

```
dnd/
├── main.py              # Game entry point and main loop
├── dnd/
│   ├── character.py     # CharacterSheet class
│   ├── character_creator.py  # Interactive character creation
│   ├── database.py      # SQLite persistence
│   ├── data.py          # Static game data
│   ├── game.py          # Dice rolling and game utilities
│   ├── dm/              # Dungeon Master AI agent
│   └── npc/             # NPC AI agents
└── tests/
    ├── test_character.py
    └── test_game.py
```
