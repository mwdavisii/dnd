# UX and Logging Improvements Design

**Date:** 2026-03-13
**Status:** Approved

## Features

### 1. Save File Naming on New Game

**Problem:** When no saves exist, `choose_save_file()` silently creates a timestamped path with no user input.

**Design:** Prompt for a name before creating:
```
Name your adventure (leave blank for timestamp) »
```
Then call `create_save_path(name or None)` as before. One-line change in `main.py`.

---

### 2. Ollama Call Timing

**Problem:** No visibility into how long each LLM call takes, making model comparison impossible.

**Design:** Wrap each `requests.post` call with `time.time()` before/after in:
- `DungeonMaster.generate_opening_scene()`
- `DungeonMaster.generate_arc()`
- `DungeonMaster.generate_response()`
- `DungeonMaster._evaluate_beat()`
- `NPCAgent.generate_response()` / `generate_action()`
- `AutoPlayerAgent.generate_action()`

Print a labeled duration to stdout immediately after each response:
```
[DM: 4.2s]   [Arc: 1.8s]   [Player: 2.3s]   [Kaelen: 1.6s]
```

Format: `style(f"[{label}: {elapsed:.1f}s]", "gray", dim=True)`

Since transcript captures stdout, timing appears in logs automatically — no extra wiring needed.

---

### 3. Structured Markdown Transcript

**Problem:** `TeeStream` dumps raw stdout (thinking messages, turn tables, ANSI noise) into a ` ```text ``` ` block. Unnavigable and unreadable.

**Design:** Replace `TeeStream` + raw file dump with an explicit `TranscriptWriter` class that writes clean structured markdown at key moments only.

#### Output Format

```markdown
# D&D Session Transcript

| | |
|---|---|
| Save | `spectator_3` |
| Started | 2026-03-13 02:54 PM |
| Model | `qwen2.5:32b` |

---

## Opening Scene *(3.2s)*

You find yourselves in the bustling town of Graysfall...

---

## Round 1

### Kraton — Player

> Follow the cloaked man to the edge of town.

### Dungeon Master *(4.1s)*

The cloaked figure ducks into an alley...

---

### Kaelen — Companion *(1.8s)*

> I keep watch on the alley entrance.

---
```

#### TranscriptWriter API

```python
class TranscriptWriter:
    def __init__(self, path: Path, save_path: str, model: str)
    def start(self) -> "TranscriptWriter"
    def stop(self)
    def write_opening_scene(self, text: str, elapsed: float)
    def write_round_header(self, round_number: int)
    def write_player_action(self, actor_name: str, action: str)
    def write_companion_action(self, actor_name: str, action: str, elapsed: float)
    def write_dm_response(self, text: str, elapsed: float)
```

#### Wiring

- `TranscriptWriter` created in `main()` if user opts in (replaces `TranscriptSession`)
- Passed into `process_dm_turn()` and `run_spectator_turn()` as optional parameter
- `TeeStream` and `TranscriptSession` removed
- `choose_transcript_logging()` updated to return `TranscriptWriter | None`

#### What gets logged (only)
- Session metadata header
- Opening scene text + timing
- Round headers
- Player actions (in blockquote)
- Companion actions (in blockquote + timing)
- DM narration + timing

#### What does NOT get logged
- Thinking messages (`<DM is thinking...>`)
- Turn order tables
- Suggested actions
- Command output (`/sheet`, `/roll`, etc.)
- Arc generation output
