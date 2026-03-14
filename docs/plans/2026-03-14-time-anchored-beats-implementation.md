# Time-Anchored Beats Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Guarantee stories reach resolution within the round budget by giving each story beat a hard deadline, loosening the beat evaluator, and making `story_phase` a direct function of `current_beat`.

**Architecture:** Three tasks, each in one file. Task 1 loosens the beat evaluation prompt. Task 2 adds forced deadline advancement and story_phase sync to the DM agent. Task 3 removes the redundant time-based story_phase from the CLI's pacing sync, replacing it with a current_beat-derived value.

**Tech Stack:** Python stdlib only. Tests use pytest with monkeypatch and MagicMock.

---

### Task 1: Loosen the beat evaluation prompt

**Files:**
- Modify: `dnd/dm/prompts.py`
- Test: `tests/test_dm_agent.py`

**Background:**

The current `BEAT_EVALUATION_PROMPT` asks "Has the success condition been **fully** met?" which almost never returns YES for a single DM turn. We change it to "Has the party made **substantial progress** toward this condition?" so organic early advancement actually fires.

**Step 1: Write the failing test**

Read `tests/test_dm_agent.py` first. Find the existing test `test_evaluate_beat_advances_on_yes` (or similar). Add a new test that verifies the prompt text contains "substantial progress":

```python
def test_beat_evaluation_prompt_uses_substantial_progress():
    from dnd.dm.prompts import BEAT_EVALUATION_PROMPT
    assert "substantial progress" in BEAT_EVALUATION_PROMPT
    assert "fully met" not in BEAT_EVALUATION_PROMPT
```

**Step 2: Run to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_beat_evaluation_prompt_uses_substantial_progress -v
```

Expected: FAIL (`"fully met" in prompt`)

**Step 3: Update `BEAT_EVALUATION_PROMPT` in `dnd/dm/prompts.py`**

Find:
```python
BEAT_EVALUATION_PROMPT = """
You are evaluating story progress in a D&D game.

Current beat success condition:
{success_condition}

What just happened in the story:
{dm_response}

Has the success condition been fully met based on what happened?
Answer with only YES or NO.
"""
```

Replace with:
```python
BEAT_EVALUATION_PROMPT = """
You are evaluating story progress in a D&D game.

Current beat success condition:
{success_condition}

What just happened in the story:
{dm_response}

Has the party made substantial progress toward this condition based on what happened?
Answer with only YES or NO.
"""
```

**Step 4: Run to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_beat_evaluation_prompt_uses_substantial_progress -v
```

**Step 5: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

Known pre-existing failure: `test_main_executes_short_spectator_game_with_two_npcs` — ignore.

**Step 6: Commit**

```bash
git add dnd/dm/prompts.py tests/test_dm_agent.py
git commit -m "fix: loosen beat evaluation from 'fully met' to 'substantial progress'"
```

---

### Task 2: Add beat deadlines and story_phase sync to `_evaluate_beat()`

**Files:**
- Modify: `dnd/dm/agent.py`
- Test: `tests/test_dm_agent.py`

**Background:**

`_evaluate_beat()` currently only advances `current_beat` when the LLM says YES. We add two things:

1. **`_beat_past_deadline()`**: returns True when the current round has crossed the beat's hard deadline ratio. Deadlines: hook=0.25, complication=0.65, climax=0.87. No LLM call needed.

2. **story_phase sync**: whenever `current_beat` advances (by LLM or deadline), immediately update `story_phase` using the mapping `hook→opening, complication→midgame, climax→climax, resolution→resolution`.

The `_evaluate_beat()` logic becomes:
1. Check deadline → if past deadline, `should_advance = True`
2. If not past deadline, run LLM evaluation → if YES, `should_advance = True`
3. If `should_advance`, advance `current_beat` and sync `story_phase`

**Step 1: Write the failing tests**

Add to `tests/test_dm_agent.py`:

```python
def test_beat_past_deadline_returns_true_when_round_exceeds_ratio(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("target_rounds", 10)
    dm.update_world_state("current_round", 4)  # 4/10 = 0.40 > hook deadline 0.25
    assert dm._beat_past_deadline("hook") is True


def test_beat_past_deadline_returns_false_before_deadline(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("target_rounds", 10)
    dm.update_world_state("current_round", 2)  # 2/10 = 0.20 < hook deadline 0.25
    assert dm._beat_past_deadline("hook") is False


def test_beat_past_deadline_returns_false_when_no_target(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("target_rounds", 0)
    dm.update_world_state("current_round", 5)
    assert dm._beat_past_deadline("hook") is False


def test_evaluate_beat_force_advances_past_deadline(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("target_rounds", 10)
    dm.update_world_state("current_round", 4)  # past hook deadline
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("story_arc", {
        "hook": {"goal": "Find the threat", "key_npcs": [], "success_condition": "Threat identified"},
        "complication": {"goal": "Deal with it", "key_npcs": [], "success_condition": "Complication resolved"},
        "climax": {"goal": "Confront", "key_npcs": [], "success_condition": "Confronted"},
        "resolution": {"goal": "Wrap up", "key_npcs": [], "success_condition": "Done"},
    })
    # No LLM call should be needed — deadline triggers it
    dm._evaluate_beat("The party investigates the mill.")
    assert dm.world_state["current_beat"] == "complication"
    assert dm.world_state["story_phase"] == "midgame"


def test_evaluate_beat_syncs_story_phase_on_llm_advance(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("target_rounds", 10)
    dm.update_world_state("current_round", 1)  # well before deadline
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("story_arc", {
        "hook": {"goal": "Find the threat", "key_npcs": [], "success_condition": "Threat identified"},
        "complication": {"goal": "Deal with it", "key_npcs": [], "success_condition": "Complication resolved"},
        "climax": {"goal": "Confront", "key_npcs": [], "success_condition": "Confronted"},
        "resolution": {"goal": "Wrap up", "key_npcs": [], "success_condition": "Done"},
    })

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "YES"}

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        dm._evaluate_beat("The party identifies the goblin threat.")

    assert dm.world_state["current_beat"] == "complication"
    assert dm.world_state["story_phase"] == "midgame"
```

**Step 2: Run to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_beat_past_deadline_returns_true_when_round_exceeds_ratio tests/test_dm_agent.py::test_beat_past_deadline_returns_false_before_deadline tests/test_dm_agent.py::test_beat_past_deadline_returns_false_when_no_target tests/test_dm_agent.py::test_evaluate_beat_force_advances_past_deadline tests/test_dm_agent.py::test_evaluate_beat_syncs_story_phase_on_llm_advance -v
```

Expected: FAIL (`_beat_past_deadline` doesn't exist)

**Step 3: Add `_beat_past_deadline()` to `dnd/dm/agent.py`**

Add this method to `DungeonMaster`, right before `_evaluate_beat()`:

```python
_BEAT_DEADLINES = {"hook": 0.25, "complication": 0.65, "climax": 0.87}
_BEAT_PHASE = {
    "hook": "opening",
    "complication": "midgame",
    "climax": "climax",
    "resolution": "resolution",
}

def _beat_past_deadline(self, current_beat: str) -> bool:
    """Return True if the current round has passed the beat's hard deadline."""
    current_round = int(self.world_state.get("current_round", 1) or 1)
    target_rounds = int(self.world_state.get("target_rounds", 0) or 0)
    if target_rounds <= 0:
        return False
    deadline_ratio = _BEAT_DEADLINES.get(current_beat)
    if deadline_ratio is None:
        return False
    return (current_round / target_rounds) >= deadline_ratio
```

Note: `_BEAT_DEADLINES` and `_BEAT_PHASE` are module-level constants, placed just before the `DungeonMaster` class definition.

**Step 4: Update `_evaluate_beat()` in `dnd/dm/agent.py`**

Replace the existing `_evaluate_beat()` with:

```python
def _evaluate_beat(self, response: str) -> None:
    """Check if the current story beat is complete and advance if so."""
    story_arc = self.world_state.get("story_arc")
    if not story_arc:
        return

    beat_order = ["hook", "complication", "climax", "resolution"]
    current_beat = str(self.world_state.get("current_beat", "hook") or "hook")
    if current_beat not in beat_order:
        return
    current_idx = beat_order.index(current_beat)
    if current_idx >= len(beat_order) - 1:
        return  # Already at resolution

    should_advance = self._beat_past_deadline(current_beat)

    if not should_advance:
        success_condition = str(story_arc.get(current_beat, {}).get("success_condition", "") or "")
        if success_condition:
            prompt = BEAT_EVALUATION_PROMPT.format(
                success_condition=success_condition,
                dm_response=response[:900],
            )
            try:
                _t0 = time.time()
                eval_response = requests.post(
                    f"{self.ollama_host}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                    },
                    timeout=(5, 30),
                )
                eval_response.raise_for_status()
                print(style(f"[Beat: {time.time() - _t0:.1f}s]", "gray", dim=True))
                raw = eval_response.json().get("response", "").strip().lower()
                if raw.startswith("yes"):
                    should_advance = True
            except requests.exceptions.RequestException:
                pass  # Silently skip on network error

    if should_advance:
        next_beat = beat_order[current_idx + 1]
        self.update_world_state("current_beat", next_beat)
        self.update_world_state("story_phase", _BEAT_PHASE[next_beat])
```

**Step 5: Run the new tests**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_beat_past_deadline_returns_true_when_round_exceeds_ratio tests/test_dm_agent.py::test_beat_past_deadline_returns_false_before_deadline tests/test_dm_agent.py::test_beat_past_deadline_returns_false_when_no_target tests/test_dm_agent.py::test_evaluate_beat_force_advances_past_deadline tests/test_dm_agent.py::test_evaluate_beat_syncs_story_phase_on_llm_advance -v
```

**Step 6: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

**Step 7: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: add beat deadlines and story_phase sync to beat evaluation"
```

---

### Task 3: Derive story_phase from current_beat in `_sync_story_pacing()`

**Files:**
- Modify: `dnd/cli/__init__.py`
- Test: `tests/test_command_handler.py`

**Background:**

`_sync_story_pacing()` currently computes `story_phase` from the round/target ratio. This creates the dual-tracker problem — it overwrites whatever `_evaluate_beat()` just set. Replace the ratio calculation with a direct lookup from `current_beat`.

**Step 1: Write the failing test**

Read `tests/test_command_handler.py` first to understand existing patterns. Add:

```python
def test_sync_story_pacing_derives_phase_from_current_beat(mock_dm):
    """story_phase must reflect current_beat, not the round ratio."""
    mock_dm.world_state = {
        "target_rounds": 10,
        "current_round": 1,
        "current_beat": "climax",  # beat says climax
    }
    mock_dm.update_world_state = lambda k, v: mock_dm.world_state.update({k: v})

    from dnd.cli import CommandHandler
    handler = CommandHandler(MagicMock(), {}, {}, mock_dm)
    # At round 1 of 10 (10%), old code would set story_phase="opening"
    # New code must use current_beat="climax" → story_phase="climax"
    assert mock_dm.world_state["story_phase"] == "climax"


def test_sync_story_pacing_defaults_phase_to_opening_when_no_beat(mock_dm):
    mock_dm.world_state = {
        "target_rounds": 10,
        "current_round": 1,
        # no current_beat set
    }
    mock_dm.update_world_state = lambda k, v: mock_dm.world_state.update({k: v})

    from dnd.cli import CommandHandler
    handler = CommandHandler(MagicMock(), {}, {}, mock_dm)
    assert mock_dm.world_state["story_phase"] == "opening"
```

**Step 2: Run to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_command_handler.py::test_sync_story_pacing_derives_phase_from_current_beat tests/test_command_handler.py::test_sync_story_pacing_defaults_phase_to_opening_when_no_beat -v
```

Expected: FAIL (old code uses ratio, returns "opening" instead of "climax")

**Step 3: Update `_sync_story_pacing()` in `dnd/cli/__init__.py`**

Find the current implementation:

```python
def _sync_story_pacing(self) -> None:
    target_rounds = int(self.dm.world_state.get("target_rounds", 0) or 0)
    self.dm.update_world_state("current_round", self.round_number)
    if target_rounds > 0:
        remaining_rounds = max(target_rounds - self.round_number, 0)
        self.dm.update_world_state("remaining_rounds", remaining_rounds)
        progress_ratio = self.round_number / target_rounds
        if progress_ratio <= 0.25:
            story_phase = "opening"
        elif progress_ratio <= 0.70:
            story_phase = "midgame"
        elif progress_ratio <= 0.90:
            story_phase = "climax"
        else:
            story_phase = "resolution"
        self.dm.update_world_state("story_phase", story_phase)
```

Replace with:

```python
_BEAT_PHASE = {
    "hook": "opening",
    "complication": "midgame",
    "climax": "climax",
    "resolution": "resolution",
}

def _sync_story_pacing(self) -> None:
    target_rounds = int(self.dm.world_state.get("target_rounds", 0) or 0)
    self.dm.update_world_state("current_round", self.round_number)
    if target_rounds > 0:
        remaining_rounds = max(target_rounds - self.round_number, 0)
        self.dm.update_world_state("remaining_rounds", remaining_rounds)
    current_beat = str(self.dm.world_state.get("current_beat", "hook") or "hook")
    story_phase = _BEAT_PHASE.get(current_beat, "opening")
    self.dm.update_world_state("story_phase", story_phase)
```

Note: `_BEAT_PHASE` is a module-level constant in `dnd/cli/__init__.py`. Place it near the top of the file, after the imports.

**Step 4: Run the new tests**

```bash
PYTHONPATH=. pytest tests/test_command_handler.py::test_sync_story_pacing_derives_phase_from_current_beat tests/test_command_handler.py::test_sync_story_pacing_defaults_phase_to_opening_when_no_beat -v
```

**Step 5: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

**Step 6: Commit**

```bash
git add dnd/cli/__init__.py tests/test_command_handler.py
git commit -m "fix: derive story_phase from current_beat instead of round ratio"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `dnd/dm/prompts.py` | `BEAT_EVALUATION_PROMPT`: "substantial progress" replaces "fully met" |
| `dnd/dm/agent.py` | Add `_BEAT_DEADLINES`, `_BEAT_PHASE` constants; add `_beat_past_deadline()`; update `_evaluate_beat()` to check deadline first, then LLM; sync `story_phase` on any advance |
| `dnd/cli/__init__.py` | Remove ratio-based `story_phase` from `_sync_story_pacing()`; derive from `current_beat` via `_BEAT_PHASE` map |
