# Story Arc Design

**Date:** 2026-03-13
**Status:** Approved

## Problem

Story arcs are ineffective and unfocused. The AI player agent wanders off the story hook (e.g., inspects a book instead of following the cloaked figure), and the DM follows along rather than steering back. Root cause: the opening scene never populates structured world state, so both agents fly blind with no real objective.

Specific failures observed:
- `_infer_opening_world_state` only extracts location (regex) and sets the first sentence as objective — not useful
- `notable_npcs`, `nearby_locations`, `story_hook` are never populated from the opening scene
- `_update_story_progress` is hardcoded to one scenario (letter, mayor, Whispering Woods)
- Player agent has no explicit goal, so it picks arbitrary actions

## Approach: Pre-generate a Story Arc (Approach B)

After the opening scene is narrated, make one LLM call to generate a structured 4-beat story arc. Both the DM and player agent receive the current beat's goal explicitly on every turn. A lightweight per-turn beat evaluator replaces the hardcoded progress tracker.

## Architecture

```
startup:
  generate_opening_scene()
    → generate_arc(opening_scene)          ← new LLM call
        → world_state: story_arc, current_beat="hook",
                       objective, notable_npcs, nearby_locations, story_hook

each turn:
  player_agent.generate_action()
    → receives current beat goal explicitly

  dm.generate_response()
    → current beat goal injected into DM prompt
    → _evaluate_beat(response)             ← new LLM call, replaces hardcoded tracker
        → if beat complete: current_beat advances
```

## Arc Structure

The arc JSON stored in `world_state["story_arc"]`:

```json
{
  "hook":         { "goal": "...", "key_npcs": [...], "success_condition": "..." },
  "complication": { "goal": "...", "key_npcs": [...], "success_condition": "..." },
  "climax":       { "goal": "...", "key_npcs": [...], "success_condition": "..." },
  "resolution":   { "goal": "...", "key_npcs": [...], "success_condition": "..." }
}
```

`world_state["current_beat"]` tracks which beat is active (starts at `"hook"`).

## Components

### New: `DungeonMaster.generate_arc(opening_scene: str)`
- Called once after `generate_opening_scene()` in `main.py`
- One LLM call: reads opening narration, outputs arc JSON + extracted fields
- Populates `world_state`: `story_arc`, `current_beat`, `objective`, `notable_npcs`, `nearby_locations`, `story_hook`
- Falls back to a generic 4-beat arc if JSON parsing fails

### New: `DungeonMaster._evaluate_beat(response: str)`
- Called after each DM response inside `generate_response()`
- One LLM call: "given this beat's success condition and what just happened, did the party make meaningful progress?"
- If True: advance `current_beat` to next beat
- Replaces `_update_story_progress()` entirely

### Modified: `DungeonMaster._dm_scene_context()`
- Injects current beat `goal` and `success_condition` into DM prompt
- Replaces vague "stay on the active thread" language with concrete beat goal

### Modified: `AutoPlayerAgent.generate_action()`
- Injects current beat goal explicitly: "Your character's current goal: [beat goal]"
- Direct fix for the wandering problem

### Modified: `build_turn_context()` in `spectator.py`
- Adds `current_beat_goal` to turn context dict
- Flows through `format_turn_context()` to the formatted context block

## What Stays the Same

- Turn order, NPC agents, combat, `CommandHandler`, all `/commands`
- Database schema (arc data lives in existing `world_state` JSON blob)
- Streaming architecture for DM responses

## New LLM Calls Per Session

- 1 at startup (arc generation)
- 1 per DM turn (beat evaluation)

## Future: Approach C

If arc adherence still breaks down mid-game, add a Scene Director agent (LangGraph candidate) that evaluates story progress after each turn and can inject mandatory narrative redirects into the next DM prompt.
