# Quest Chaining System — Design Spec

**Date:** 2026-03-17
**Status:** Approved

## Problem

The game currently runs for a fixed number of rounds and ends. Level up, rest, and shopping mechanics exist in the codebase but never trigger during normal play because the game terminates before a natural break point occurs. The story arc's `<ending>` tag and `story_complete` flag fire at narrative resolution, but nothing happens afterward — the game just waits out remaining rounds or ends abruptly.

## Goal

Replace the fixed-round termination model with a quest-chaining system. When a quest completes, the game flows through epilogue → downtime narration → player between-quest choices → new quest. Each quest is a direct narrative continuation of the last, using the same characters and a world that remembers what happened.

## Approach

Hybrid world state carry-forward with campaign summary compression (Approach C). On quest completion, the current story is compressed into a `campaign_summary` (~300 words) and appended to a persistent `campaign_history` list. Operational state is reset. Continuity data (characters, notable NPCs, locations, resolved events) carries forward. The new arc generator receives only the most recent campaign summary as prior context — so context cost stays flat across any number of quests.

---

## Overall Flow

```
Quest ends (ending tag fires OR story_complete = True)
  │
  ▼
Epilogue narration  [existing]
  │
  ▼
generate_campaign_summary()  [NEW]
  └─ compresses story into ~300 words, appended to campaign_history list
  │
  ▼
generate_downtime_scene()  [NEW]
  └─ 1-2 paragraph LLM narration of rest period, printed to screen
  │
  ▼
Between-Quest menu  [NEW — guided, sequential]
  ├─ Level Up (if eligible) → existing /levelup flow with player choices
  ├─ Rest → existing /rest flow
  └─ Shop → existing /shop flow
  │
  ▼
reset_for_new_quest()  [NEW]
  └─ wipes operational state, carries forward characters + capped world data
  │
  ▼
generate_opening_scene()  [modified — receives optional campaign context]
generate_arc()            [modified — receives optional campaign context]
  │
  ▼
Normal game loop resumes
```

---

## New Components

### `DungeonMaster.generate_campaign_summary()`

- Called once, immediately after epilogue
- Reads all inputs from `self.world_state`: `story_summary`, `resolved_events`, `notable_npcs`, `ending_type`, and the resolution beat goal from `story_arc["resolution"]["goal"]` — consistent with how `generate_epilogue()` and `_update_story_summary()` work
- Makes one non-streaming Ollama call using `CAMPAIGN_SUMMARY_PROMPT`
- Output: ~300-word compressed narrative prose covering what happened, who was involved, what was resolved, what threads remain open
- Appended to `world_state["campaign_history"]` via `update_world_state()` — this persists to the DB automatically via `save_world_state()`, so campaign history survives save-file reloads
- Only the most recent entry is ever passed to the next arc generator; the list is intentionally uncapped in the DB since it has no LLM cost impact

### `DungeonMaster.generate_downtime_scene()`

- Called after campaign summary is saved
- Reads inputs from `self.world_state`: latest campaign summary (last entry of `campaign_history`), `ending_type`, `player_name`
- Makes one non-streaming Ollama call using `DOWNTIME_SCENE_PROMPT`
- Output: 2-3 paragraph narration of the recovery period — where the party rests, how the world reacts, a sense of time passing
- Printed to screen like the opening scene; also recorded via `TranscriptWriter` if active
- No player input; purely narrative

### Between-Quest menu (new function `run_between_quest_menu()` in `main.py`)

A sequential guided flow, not a free-form command loop:

1. Print "Time passes. Before your next adventure..." header
2. **Level Up:** If `player_sheet.level < MAX_LEVEL` (constant = 20, added to `dnd/data.py`), invoke `run_level_up_menu()` (new helper, see below)
3. **Rest:** Prompt "Do you want to take a long rest? (y/n)". If yes, call `handler.handle("/longrest")`
4. **Shop:** Prompt "Do you want to visit the shop? (y/n)". If yes, print shop inventory via `handler.handle("/shop")`, then enter a buy loop: accept `/buy <item>` commands until the player enters an empty line or `done`
5. Print "Press Enter to begin your next quest." and wait for input

**`run_level_up_menu()` (new helper in `main.py`):**

No `/levelup` command exists today — `CharacterSheet.level_up(new_max_hp_increase)` takes a flat integer HP increase only and has no interactive flow. This helper must be written as new scope:
- Determine eligible ability score improvements and new spells based on class and new level (using `CLASS_DATA` from `dnd/data.py`)
- Prompt player to choose ability score improvement or feat (if applicable)
- Prompt player to choose new spells from class spell list (if applicable)
- Roll HP: use `player_sheet.hit_die_type` (e.g. `d12` for Barbarian) + player's CON modifier (minimum 1), pass result as `new_max_hp_increase` to `player_sheet.level_up()`
- Print confirmation

Level cap is 20 (D&D 5e standard). A `MAX_LEVEL = 20` constant will be added to `dnd/data.py`.

### `DungeonMaster.reset_for_new_quest()`

Resets operational state, preserves continuity. Also clears `self.history` (the in-memory conversation list) so the new quest starts with a clean context window — the campaign summary preserves narrative continuity without carrying forward raw turn-by-turn history. NPC agents hold their own `self.history` lists; main.py must also clear these on each `NPCAgent` instance. NPC `memory` (loaded from DB) is preserved and carries forward as-is.

`opening_scene` and `story_arc` are both explicitly listed as reset — this ensures the early-return skip guards in `generate_opening_scene()` and `generate_arc()` do not suppress regeneration on the new quest.

| Reset | Carry Forward |
|-------|--------------|
| `story_arc`, `current_beat`, `story_phase` | `notable_npcs` (capped at 6) |
| `current_round`, `remaining_rounds` | `nearby_locations` (kept as known places) |
| `story_summary`, `scene_summary` | `resolved_events` (capped at 12) |
| `story_complete`, `ending_type` | `campaign_history` (full list, persisted to DB) |
| `opening_scene`, `objective`, `location` | `target_rounds` (player pacing preference) |
| `pending_encounter_enemies`, `pending_roll` | character stats (in DB, untouched) |
| `scene_stall_count`, `recent_party_actions` | NPC memories (in DB, untouched) |
| `self.history` (DM conversation list) | |
| each `NPCAgent.history` (via main.py) | |

---

## Changes to Existing Components

### `generate_arc()` and `generate_opening_scene()`

Both receive an optional `campaign_context: str` parameter (defaults to `""`). When present, the context is injected as "Previous quest summary: ..." — but the injection method differs per function due to their different prompt-building patterns:

- **`generate_arc()`** uses `ARC_GENERATION_PROMPT.format(...)`. A new `{campaign_context}` format slot is added at the top of `ARC_GENERATION_PROMPT`. The slot renders as an empty string on the first quest.
- **`generate_opening_scene()`** builds `full_prompt` by string concatenation. The campaign context block is prepended to `full_prompt` before `OPENING_SCENE_PROMPT` when non-empty.

When absent (first quest), behavior is identical to today in both cases.

### `ARC_GENERATION_PROMPT`

New optional slot at the top:
```
{campaign_context}
Given the above history, generate a new 4-beat arc that continues the story...
```
Empty string when first quest, populated on subsequent ones.

### `OPENING_SCENE_PROMPT`

No change to the prompt template itself. The campaign context is injected via string prepend in `generate_opening_scene()` before `OPENING_SCENE_PROMPT` is appended to `full_prompt`.

### New prompts in `dnd/dm/prompts.py`

- `CAMPAIGN_SUMMARY_PROMPT` — compress completed quest into ~300 words: what happened, who was involved, what resolved, what threads remain open
- `DOWNTIME_SCENE_PROMPT` — narrate a brief recovery period bridging the two quests

### Quest completion trigger in `main.py`

Currently epilogue only fires when `current_round > target_rounds`. Add a second trigger: when `dm.story_is_complete()` returns `True` mid-game (ending tag fired before round limit). Both paths converge into the same post-quest flow.

---

## Context Size Analysis

The new arc generator receives:
- `campaign_context`: ~300 words (~400 tokens)
- `notable_npcs`: max 6 names (~30 tokens)
- `nearby_locations`: max 6 names (~30 tokens)

Total additional context per new quest: ~460 tokens above baseline. Cost stays flat across all quests because only the most recent campaign summary is passed, not the full history list.

---

## Error Handling

- `generate_campaign_summary()` failure: fall back to using the `EVENTS SO FAR:` block extracted from `story_summary` as campaign context (avoid passing the full structured summary format since the arc generator expects narrative prose)
- `generate_downtime_scene()` failure: print a generic "The party rests and recovers before the next adventure." fallback
- `run_level_up_menu()`: if `CLASS_DATA` does not define spells for the class/level, skip the spell selection step silently
- `run_between_quest_menu()`: each step is independently skippable; a failure in one step does not block the others
- `reset_for_new_quest()`: pure state mutation, no LLM call, no failure path

---

## Testing

- Unit test `reset_for_new_quest()`: verify reset keys are cleared, carry-forward keys are preserved, `self.history` is empty after reset
- Unit test `generate_campaign_summary()` with mocked Ollama: verify output appended to `campaign_history` and persisted via `save_world_state`
- Unit test `run_level_up_menu()`: verify correct prompts appear for classes with/without spell choices; verify `level_up()` called with correct HP delta
- Integration test full quest-chain flow: trigger `story_complete`, verify campaign summary saved, downtime fires, between-quest menu presented, new arc generated with `campaign_context` populated
- Existing arc + opening scene tests: verify no regression when `campaign_context` is empty string (first quest)
