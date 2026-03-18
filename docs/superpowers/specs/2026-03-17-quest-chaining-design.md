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
- Inputs: `story_summary`, `resolved_events`, `notable_npcs`, `ending_type`, resolution beat goal
- Makes one non-streaming Ollama call using `CAMPAIGN_SUMMARY_PROMPT`
- Output: ~300-word compressed narrative covering what happened, who was involved, what was resolved, what threads remain open
- Appended to `world_state["campaign_history"]` as a list (one entry per completed quest)
- Only the most recent entry is ever passed to the next arc generator

### `DungeonMaster.generate_downtime_scene()`

- Called after campaign summary is saved
- Inputs: latest campaign summary, ending type, player name
- Makes one non-streaming Ollama call using `DOWNTIME_SCENE_PROMPT`
- Output: 2-3 paragraph narration of the recovery period — where the party rests, how the world reacts, a sense of time passing
- Printed to screen like the opening scene
- No player input; purely narrative

### Between-Quest menu (new function in `main.py`)

A sequential guided flow, not a free-form command loop:

1. Print "Time passes. Before your next adventure..." header
2. If player is eligible to level up: automatically enter level-up flow (player chooses abilities/spells)
3. Prompt: "Do you want to rest? (y/n)" → invoke `/rest`
4. Prompt: "Do you want to visit the shop? (y/n)" → invoke `/shop`
5. "Press Enter to begin your next quest."

Uses existing `CommandHandler` methods — no new mechanics introduced.

### `DungeonMaster.reset_for_new_quest()`

Resets operational state, preserves continuity:

| Reset | Carry Forward |
|-------|--------------|
| `story_arc`, `current_beat`, `story_phase` | `notable_npcs` (capped at 6) |
| `current_round`, `remaining_rounds` | `nearby_locations` (kept as known places) |
| `story_summary`, `scene_summary` | `resolved_events` (capped at 12) |
| `story_complete`, `ending_type` | `campaign_history` (full list) |
| `opening_scene`, `objective`, `location` | `target_rounds` (player pacing preference) |
| `pending_encounter_enemies`, `pending_roll` | character stats (in DB, untouched) |
| `scene_stall_count`, `recent_party_actions` | |

---

## Changes to Existing Components

### `generate_arc()` and `generate_opening_scene()`

Both receive an optional `campaign_context: str` parameter (defaults to `""`). When present, prepended to the prompt as "Previous quest summary: ...". When absent (first quest), behavior is identical to today.

### `ARC_GENERATION_PROMPT`

New optional section at the top:
```
{campaign_context}
Given the above history, generate a new 4-beat arc that continues the story...
```
Empty string when first quest, populated on subsequent ones.

### `OPENING_SCENE_PROMPT`

Same treatment: optional campaign context block prepended.

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

- `generate_campaign_summary()` failure: skip silently, use `story_summary` directly as campaign context
- `generate_downtime_scene()` failure: print a generic "The party rests and recovers before the next adventure." fallback
- Between-quest menu: each step (level up / rest / shop) uses existing error handling in CommandHandler
- `reset_for_new_quest()`: pure state mutation, no LLM call, no failure path

---

## Testing

- Unit test `reset_for_new_quest()`: verify reset keys are cleared, carry-forward keys are preserved
- Unit test `generate_campaign_summary()` with mocked Ollama: verify output appended to `campaign_history`
- Integration test full quest-chain flow: trigger `story_complete`, verify downtime fires, verify new arc generated with `campaign_context` populated
- Existing arc + opening scene tests: verify no regression when `campaign_context` is empty string
