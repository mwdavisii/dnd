# Time-Anchored Beats Design

**Date:** 2026-03-14

## Problem

Stories reliably fail to reach resolution within a 10-round session. Two root causes:

1. **Two conflicting progress trackers.** `story_phase` is purely time-based (round/target ratio). `current_beat` is event-based (LLM evaluator). The DM prompt sees both simultaneously. When they disagree — e.g., story_phase="midgame" but current_beat="hook" — the DM gets contradictory signals about where the story should be.

2. **Beat evaluator is too strict.** `BEAT_EVALUATION_PROMPT` asks "Has the success condition been *fully* met?" A single DM turn almost never fully satisfies a multi-element condition like "The party discovers the Skyweaver connection AND knows where to go." Answer is nearly always NO. So `current_beat` stays frozen on "hook" the entire run.

## Design

### 1. Hard Beat Deadlines (guaranteed resolution)

Each beat owns a fixed slice of the round budget. When the current round crosses the deadline ratio, the beat force-advances — no LLM evaluation needed.

| Beat | Deadline ratio | 10-round example |
|------|---------------|-----------------|
| hook | 25% | closes at round 3 |
| complication | 65% | closes at round 7 |
| climax | 87% | closes at round 9 |
| resolution | — | rounds 9-10 |

The LLM evaluator can still advance a beat *early* — deadlines are a floor, not a ceiling.

### 2. Looser Beat Evaluation

Change `BEAT_EVALUATION_PROMPT` from:
> "Has the success condition been fully met?"

to:
> "Has the party made substantial progress toward this condition?"

This allows organic early advancement when the story naturally earns it.

### 3. Single Source of Truth

Remove the separate time-based `story_phase` derivation from `_sync_story_pacing()`. Instead, `story_phase` is always derived from `current_beat` via a fixed mapping:

| current_beat | story_phase |
|---|---|
| hook | opening |
| complication | midgame |
| climax | climax |
| resolution | resolution |

`_sync_story_pacing()` sets `story_phase` from the current beat on every sync (handles saved game load correctly). `_evaluate_beat()` also sets `story_phase` immediately when a beat advances (immediate DM feedback).

## Files Changed

| File | Change |
|------|--------|
| `dnd/dm/prompts.py` | Loosen `BEAT_EVALUATION_PROMPT` wording |
| `dnd/dm/agent.py` | Add `_beat_past_deadline()`, update `_evaluate_beat()` to force-advance and sync story_phase |
| `dnd/cli/__init__.py` | Remove time-based story_phase from `_sync_story_pacing()`; derive from current_beat instead |
