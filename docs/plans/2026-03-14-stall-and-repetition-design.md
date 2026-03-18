# Scene Stalling & Companion Repetition Fixes

**Date:** 2026-03-14

## Problem 1: Scene Stalling

DM repeats the same standoff for 5+ rounds because `detect_scene_stall()` uses raw token overlap (≥55%) on scene summaries, which misses semantically identical scenes worded differently.

**Fix:** Compare OPEN THREADS from the rolling story summary across rounds. If threads are unchanged (≥70% overlap) for 2+ rounds, the scene is stalled.

## Problem 2: Companion Repetition

Companions repeat nearly identical actions ("Stand down") because duplicate detection uses exact normalized text match and companions don't see their own recent actions.

**Fix:** Track per-companion action history, inject it into prompts with "do NOT repeat" instruction, and use fuzzy token overlap (≥50%) for duplicate detection instead of exact match.

## Files Changed

| File | Change |
|---|---|
| `dnd/spectator.py` | Add `extract_open_threads()`, update `detect_scene_stall()`, add fuzzy dedup to `validate_turn_output()` |
| `dnd/npc/agent.py` | Add `self.recent_actions`, inject into prompt, pass to validation |
| `main.py` | Pass story summary to `detect_scene_stall()` |
| Tests | Update stall detection and add fuzzy dedup tests |
