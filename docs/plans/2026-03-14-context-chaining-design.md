# Context Chaining: Rolling Story Summary

**Date:** 2026-03-14
**Problem:** DM story arcs suffer from disconnected resolution, flat escalation, and repetition because the LLM context is too shallow (6 messages at 140 chars + 220-char scene snapshot).

## Approach

A **rolling story summary** (~400-600 chars structured text) persisted in `world_state["story_summary"]` and updated via LLM after every DM turn.

### Summary Format

```
EVENTS SO FAR:
- (chronological bullet points of key plot beats)

OPEN THREADS:
- (things introduced but not yet resolved)

ESCALATION LEVEL: (one sentence)
```

### Update Mechanism

After every `generate_response()` call (post `_evaluate_beat()`), a new `_update_story_summary()` method makes a non-streaming LLM call with:
- Previous `story_summary`
- Player action this turn
- DM response (truncated ~800 chars)
- Current beat and arc goal

Rules enforced by prompt:
- Max 8 event bullets, max 5 open threads
- Remove resolved threads
- No restating existing events
- Under 400 words total

### Prompt Integration

DM prompt changes from:
```
"Recent story beats:\n{_recent_history_summary()}"
```
To:
```
"Story so far:\n{story_summary}\n\nLast turn:\n{_recent_history_summary()}"
```

`_recent_history_summary()` trimmed to last 2-3 entries. `scene_summary` stays for stall detection.

Story summary also fed to player agent and NPC agents for coherence.

## Files Changed

| File | Change |
|---|---|
| `dnd/dm/prompts.py` | Add `STORY_SUMMARY_PROMPT` |
| `dnd/dm/agent.py` | Add `_update_story_summary()`, call after `_evaluate_beat()`, integrate into DM prompt |
| `dnd/npc/agent.py` | Pass `story_summary` into turn action prompts |
| `dnd/spectator.py` | Include `story_summary` in `build_turn_context()` |
| `main.py` | Pass `story_summary` where needed |

No new files, no new dependencies, no schema changes.

## Fallback

If this approach doesn't produce good results with qwen2.5, explore LangGraph for structured context/state tracking.
