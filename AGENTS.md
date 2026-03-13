# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `dnd/`. Keep domain logic in focused modules such as `character.py`, `database.py`, `game.py`, and `data.py`. AI agents are split by role under `dnd/dm/` and `dnd/npc/`. The CLI entrypoint is `main.py`. Tests live in `tests/` and mirror the package by behavior, for example `tests/test_game.py` and `tests/test_character.py`. Runtime state is stored in `dnd_game.db`; treat it as generated local data, not source.

## Build, Test, and Development Commands
Create an environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the game locally with `python3 main.py`.
Run tests with `PYTHONPATH=. pytest` or `.venv/bin/python -m pytest -q`.
Before testing game flows, copy `.env.example` to `.env` and set `OLLAMA_HOST` and `OLLAMA_MODEL`.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and short docstrings where behavior is not obvious. Keep modules small and single-purpose. Prefer explicit imports from `dnd.*` modules over wildcard imports. Match existing command and prompt naming, such as `ADVENTURE_START_PROMPT` for constants.

## Testing Guidelines
Use `pytest` for all tests. Name files `test_*.py` and test functions `test_*`. Add or update tests with every behavior change, especially for dice parsing, command handling, persistence, and NPC/DM integration boundaries. Keep tests deterministic and avoid real network calls to Ollama; mock external interactions when needed.

## Commit & Pull Request Guidelines
Current history uses short imperative commit subjects, for example `Fix missing items: ...`. Keep subjects concise and action-oriented; add a colon only when it improves clarity. Pull requests should include a brief summary, the user-facing impact, test coverage notes, and linked issues if applicable. Include screenshots or terminal transcripts only when CLI output changes materially.

## Configuration & Data Tips
Do not commit secrets from `.env`. Avoid committing local database churn from `dnd_game.db` unless the change intentionally updates checked-in fixture data.
