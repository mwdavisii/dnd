# Story Arc Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Pre-generate a 4-beat story arc after the opening scene so both the DM and player agent have an explicit goal each turn, eliminating wandering and ensuring the story reaches a satisfying conclusion.

**Architecture:** After `generate_opening_scene()`, a new `generate_arc()` LLM call produces a structured 4-beat arc (hook → complication → climax → resolution) stored in `world_state`. Each turn, the DM and player agent receive the current beat's goal explicitly. A new `_evaluate_beat()` LLM call after each DM response replaces the hardcoded `_update_story_progress()`.

**Tech Stack:** Python, Ollama via `requests`, SQLite (`world_state` JSON blob), pytest with `monkeypatch` and `unittest.mock`

---

### Task 1: Add prompts for arc generation and beat evaluation

**Files:**
- Modify: `dnd/dm/prompts.py`

**Step 1: Add the two new prompts**

Append to `dnd/dm/prompts.py`:

```python
ARC_GENERATION_PROMPT = """
You are analyzing the opening scene of a D&D adventure to create a structured story arc.

Opening scene:
{opening_scene}

Generate a 4-beat story arc that fits naturally from this opening. Also extract key world state.

Respond with ONLY valid JSON — no explanation, no markdown fences, no extra text:

{{
  "objective": "The player's immediate actionable goal (one sentence, verb-first)",
  "story_hook": "The central mystery or conflict introduced in the opening",
  "notable_npcs": ["Name of NPC 1", "Name of NPC 2"],
  "nearby_locations": ["Location 1", "Location 2"],
  "arc": {{
    "hook": {{
      "goal": "What the party must do to pursue the opening hook (verb-first, one sentence)",
      "key_npcs": ["NPC names relevant to this beat"],
      "success_condition": "Specific observable event that means this beat is complete"
    }},
    "complication": {{
      "goal": "How the party must respond as the situation escalates",
      "key_npcs": [],
      "success_condition": "Specific observable event that means this beat is complete"
    }},
    "climax": {{
      "goal": "The decisive action that resolves or confronts the central conflict",
      "key_npcs": [],
      "success_condition": "Specific observable event that means this beat is complete"
    }},
    "resolution": {{
      "goal": "Wrap up the conflict and show its consequences",
      "key_npcs": [],
      "success_condition": "The story has reached a clear ending"
    }}
  }}
}}
"""

BEAT_EVALUATION_PROMPT = """
You are evaluating story progress in a D&D game.

Current beat success condition:
{success_condition}

What just happened in the story:
{dm_response}

Did the party make meaningful, concrete progress toward the success condition?
Answer with only YES or NO.
"""
```

**Step 2: Verify the file looks right**

```bash
PYTHONPATH=. python3 -c "from dnd.dm.prompts import ARC_GENERATION_PROMPT, BEAT_EVALUATION_PROMPT; print('OK')"
```
Expected: `OK`

**Step 3: Commit**

```bash
git add dnd/dm/prompts.py
git commit -m "feat: add arc generation and beat evaluation prompts"
```

---

### Task 2: Implement `DungeonMaster.generate_arc()`

**Files:**
- Modify: `dnd/dm/agent.py`
- Modify: `tests/test_dm_agent.py`

**Step 1: Write the failing tests**

Add to `tests/test_dm_agent.py`:

```python
import json


def test_generate_arc_populates_world_state(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    arc_payload = {
        "objective": "Follow the cloaked figure before he leaves town.",
        "story_hook": "A mysterious cloaked man is leaving the inn in a hurry.",
        "notable_npcs": ["Cloaked Man", "Innkeeper"],
        "nearby_locations": ["Town Gate", "Market Square"],
        "arc": {
            "hook": {
                "goal": "Follow the cloaked man to discover where he is going.",
                "key_npcs": ["Cloaked Man"],
                "success_condition": "The party learns where the man is headed or confronts him.",
            },
            "complication": {
                "goal": "Uncover the secret the man is hiding.",
                "key_npcs": ["Cloaked Man", "Innkeeper"],
                "success_condition": "The party discovers the threat to the town.",
            },
            "climax": {
                "goal": "Confront the main threat directly.",
                "key_npcs": ["Cloaked Man"],
                "success_condition": "The party defeats or neutralizes the threat.",
            },
            "resolution": {
                "goal": "Resolve the aftermath and show consequences.",
                "key_npcs": [],
                "success_condition": "The story reaches a clear ending.",
            },
        },
    }

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": json.dumps(arc_payload)}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        dm.generate_arc("You see a cloaked figure leaving the inn.")

    assert dm.world_state["current_beat"] == "hook"
    assert dm.world_state["story_arc"]["hook"]["goal"] == "Follow the cloaked man to discover where he is going."
    assert dm.world_state["objective"] == "Follow the cloaked figure before he leaves town."
    assert "Cloaked Man" in dm.world_state["notable_npcs"]
    assert "Town Gate" in dm.world_state["nearby_locations"]


def test_generate_arc_falls_back_on_bad_json(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "not valid json at all"}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        dm.generate_arc("You see a cloaked figure leaving the inn.")

    assert dm.world_state["current_beat"] == "hook"
    assert "hook" in dm.world_state["story_arc"]
    assert "complication" in dm.world_state["story_arc"]
    assert "climax" in dm.world_state["story_arc"]
    assert "resolution" in dm.world_state["story_arc"]


def test_generate_arc_skips_if_arc_already_exists(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("story_arc", {"hook": {"goal": "existing"}})

    with patch("dnd.dm.agent.requests.post") as mock_post:
        dm.generate_arc("Some opening scene.")

    mock_post.assert_not_called()
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_arc_populates_world_state tests/test_dm_agent.py::test_generate_arc_falls_back_on_bad_json tests/test_dm_agent.py::test_generate_arc_skips_if_arc_already_exists -v
```
Expected: FAIL with `AttributeError: 'DungeonMaster' object has no attribute 'generate_arc'`

**Step 3: Implement `generate_arc()` and `_set_fallback_arc()` in `dnd/dm/agent.py`**

Add the import at the top of `agent.py` (it already imports `json` and `re`):
```python
from dnd.dm.prompts import ARC_GENERATION_PROMPT, BEAT_EVALUATION_PROMPT, OPENING_SCENE_PROMPT, SYSTEM_PROMPT
```

Add these two methods to `DungeonMaster`, after `generate_opening_scene()`:

```python
def generate_arc(self, opening_scene: str) -> None:
    """Generate a 4-beat story arc from the opening scene. Skips if arc already exists (saved game)."""
    if self.world_state.get("story_arc"):
        return

    prompt = ARC_GENERATION_PROMPT.format(opening_scene=opening_scene)
    try:
        print(thinking_message("Generating story arc"))
        response = requests.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=(5, 120),
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        arc_data = json.loads(json_match.group() if json_match else raw)

        self.update_world_state("story_arc", arc_data.get("arc", {}))
        self.update_world_state("current_beat", "hook")
        if arc_data.get("objective"):
            self.update_world_state("objective", arc_data["objective"])
        if arc_data.get("notable_npcs"):
            self.update_world_state("notable_npcs", arc_data["notable_npcs"])
        if arc_data.get("nearby_locations"):
            self.update_world_state("nearby_locations", arc_data["nearby_locations"])
        if arc_data.get("story_hook"):
            self.update_world_state("story_hook", arc_data["story_hook"])
    except (requests.exceptions.RequestException, json.JSONDecodeError, AttributeError):
        self._set_fallback_arc()

def _set_fallback_arc(self) -> None:
    """Set a generic 4-beat arc when arc generation fails."""
    objective = str(self.world_state.get("objective", "Investigate the situation") or "Investigate the situation")
    fallback = {
        "hook": {
            "goal": f"Pursue the opening lead: {objective}",
            "key_npcs": [],
            "success_condition": "The party identifies the main threat or mystery.",
        },
        "complication": {
            "goal": "Overcome the first obstacle blocking your path.",
            "key_npcs": [],
            "success_condition": "The party faces a setback or discovers a deeper problem.",
        },
        "climax": {
            "goal": "Confront the main threat directly.",
            "key_npcs": [],
            "success_condition": "The main conflict reaches a decisive moment.",
        },
        "resolution": {
            "goal": "Resolve the conflict and show its consequences.",
            "key_npcs": [],
            "success_condition": "The story reaches a clear conclusion.",
        },
    }
    self.update_world_state("story_arc", fallback)
    self.update_world_state("current_beat", "hook")
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_arc_populates_world_state tests/test_dm_agent.py::test_generate_arc_falls_back_on_bad_json tests/test_dm_agent.py::test_generate_arc_skips_if_arc_already_exists -v
```
Expected: PASS

**Step 5: Run the full test suite to check for regressions**

```bash
PYTHONPATH=. pytest -v
```
Expected: All previously passing tests still pass.

**Step 6: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: implement generate_arc() with fallback and saved-game skip"
```

---

### Task 3: Implement `_evaluate_beat()`, replacing `_update_story_progress()`

**Files:**
- Modify: `dnd/dm/agent.py`
- Modify: `tests/test_dm_agent.py`

**Step 1: Write the failing tests**

Add to `tests/test_dm_agent.py`:

```python
def test_evaluate_beat_advances_on_yes(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("story_arc", {
        "hook": {"goal": "Follow the man.", "key_npcs": [], "success_condition": "Party confronts the cloaked man."},
        "complication": {"goal": "Dig deeper.", "key_npcs": [], "success_condition": "Party finds the secret."},
    })

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "YES"}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        dm._evaluate_beat("You catch up to the cloaked man and confront him in the alley.")

    assert dm.world_state["current_beat"] == "complication"


def test_evaluate_beat_stays_on_no(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("story_arc", {
        "hook": {"goal": "Follow the man.", "key_npcs": [], "success_condition": "Party confronts the cloaked man."},
        "complication": {"goal": "Dig deeper.", "key_npcs": [], "success_condition": "Party finds the secret."},
    })

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "NO"}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        dm._evaluate_beat("You look at a book in a shop window.")

    assert dm.world_state["current_beat"] == "hook"


def test_evaluate_beat_noop_when_no_arc(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    with patch("dnd.dm.agent.requests.post") as mock_post:
        dm._evaluate_beat("Something happened.")

    mock_post.assert_not_called()


def test_evaluate_beat_does_not_advance_past_resolution(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("current_beat", "resolution")
    dm.update_world_state("story_arc", {
        "resolution": {"goal": "End it.", "key_npcs": [], "success_condition": "Story ends."},
    })

    with patch("dnd.dm.agent.requests.post") as mock_post:
        dm._evaluate_beat("The adventure concludes.")

    mock_post.assert_not_called()
    assert dm.world_state["current_beat"] == "resolution"
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_evaluate_beat_advances_on_yes tests/test_dm_agent.py::test_evaluate_beat_stays_on_no tests/test_dm_agent.py::test_evaluate_beat_noop_when_no_arc tests/test_dm_agent.py::test_evaluate_beat_does_not_advance_past_resolution -v
```
Expected: FAIL with `AttributeError: 'DungeonMaster' object has no attribute '_evaluate_beat'`

**Step 3: Add `_evaluate_beat()` to `dnd/dm/agent.py`**

Add after `_set_fallback_arc()`:

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
        return  # Already at resolution, nothing to advance to

    success_condition = str(story_arc.get(current_beat, {}).get("success_condition", "") or "")
    if not success_condition:
        return

    prompt = BEAT_EVALUATION_PROMPT.format(
        success_condition=success_condition,
        dm_response=response[:600],
    )
    try:
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
        raw = eval_response.json().get("response", "").strip().lower()
        if raw.startswith("yes"):
            next_beat = beat_order[current_idx + 1]
            self.update_world_state("current_beat", next_beat)
    except requests.exceptions.RequestException:
        pass  # Silently skip on network error
```

**Step 4: Replace `_update_story_progress()` call in `generate_response()`**

In `generate_response()`, find this line:
```python
self._update_story_progress(prompt, cleaned_response)
```
Replace it with:
```python
self._evaluate_beat(cleaned_response)
```

**Step 5: Delete the now-unused `_update_story_progress()` method from `agent.py`**

Remove the entire `_update_story_progress` method (lines ~370–395).

**Step 6: Update the test that tested the old method**

In `tests/test_dm_agent.py`, find `test_update_story_progress_tracks_resolved_events_and_location` and delete it — it tested hardcoded scenario logic that no longer exists.

**Step 7: Run the new tests**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_evaluate_beat_advances_on_yes tests/test_dm_agent.py::test_evaluate_beat_stays_on_no tests/test_dm_agent.py::test_evaluate_beat_noop_when_no_arc tests/test_dm_agent.py::test_evaluate_beat_does_not_advance_past_resolution -v
```
Expected: PASS

**Step 8: Run full suite**

```bash
PYTHONPATH=. pytest -v
```
Expected: All tests pass (the deleted test is gone, no regressions).

**Step 9: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: replace hardcoded _update_story_progress with LLM-based _evaluate_beat"
```

---

### Task 4: Inject current beat goal into the DM's prompt

**Files:**
- Modify: `dnd/dm/agent.py`
- Modify: `tests/test_dm_agent.py`

**Step 1: Write the failing test**

Add to `tests/test_dm_agent.py`:

```python
def test_generate_response_includes_current_beat_goal(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("story_arc", {
        "hook": {
            "goal": "Follow the cloaked man to discover where he is going.",
            "key_npcs": ["Cloaked Man"],
            "success_condition": "Party confronts the cloaked man.",
        }
    })
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("target_rounds", 10)
    dm.update_world_state("remaining_rounds", 9)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.iter_lines.return_value = [
        b'{"response":"The cloaked man turns a corner.","done":false}',
        b'{"done":true}',
    ]

    with patch("dnd.dm.agent.requests.post", return_value=fake_response) as mock_post:
        # Suppress the _evaluate_beat LLM call
        with patch.object(dm, "_evaluate_beat"):
            dm.generate_response("Follow him.", player_sheet, {})

    prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "Follow the cloaked man to discover where he is going." in prompt
    assert "Current beat goal:" in prompt
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_includes_current_beat_goal -v
```
Expected: FAIL

**Step 3: Add `_current_beat_goal()` helper and update `_dm_scene_context()` in `agent.py`**

Add helper method to `DungeonMaster`:

```python
def _current_beat_goal(self) -> str:
    """Return the goal for the current story beat."""
    story_arc = self.world_state.get("story_arc") or {}
    current_beat = str(self.world_state.get("current_beat", "hook") or "hook")
    beat_data = story_arc.get(current_beat) or {}
    return str(beat_data.get("goal", "") or "")
```

In `_dm_scene_context()`, find the return statement and add `Current beat goal:` just before `Arc pressure:`:

```python
return (
    "Current turn context:\n"
    f"{format_turn_context(turn_context)}\n"
    f"Submitted action: {prompt}\n"
    f"Pending roll: {pending_roll_text}\n"
    f"Current beat goal: {self._current_beat_goal()}\n"
    f"Arc pressure: {self._arc_pressure_instruction()}\n"
    f"Objective lock: {self._objective_lock_instruction()}"
)
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_includes_current_beat_goal -v
```
Expected: PASS

**Step 5: Run full suite**

```bash
PYTHONPATH=. pytest -v
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: inject current beat goal into DM prompt each turn"
```

---

### Task 5: Add current beat goal to turn context in `spectator.py`

**Files:**
- Modify: `dnd/spectator.py`
- Modify: `tests/test_dm_agent.py` (reuse dm_db fixture pattern) or create a focused test inline

**Step 1: Write the failing test**

Add to `tests/test_dm_agent.py` (it already imports what we need):

```python
from dnd.spectator import build_turn_context, format_turn_context


def test_build_turn_context_includes_current_beat_goal(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    world_state = {
        "story_arc": {
            "hook": {
                "goal": "Follow the cloaked man.",
                "key_npcs": [],
                "success_condition": "Party confronts the cloaked man.",
            }
        },
        "current_beat": "hook",
        "target_rounds": 10,
        "current_round": 1,
        "remaining_rounds": 9,
    }

    ctx = build_turn_context(world_state, "Kraton", "player", "No summary yet.")
    assert ctx["current_beat_goal"] == "Follow the cloaked man."


def test_format_turn_context_includes_beat_goal():
    ctx = {
        "actor_name": "Kraton",
        "actor_type": "player",
        "location": "Graysfall",
        "objective": "Follow the man.",
        "story_phase": "opening",
        "current_round": 1,
        "target_rounds": 10,
        "remaining_rounds": 9,
        "phase_goal": "Commit to the hook.",
        "scene_momentum": "steady",
        "immediate_danger": "None",
        "scene_summary": "The scene begins.",
        "recent_party_actions": [],
        "last_progress_events": [],
        "resolved_events": [],
        "notable_npcs": [],
        "nearby_locations": [],
        "current_beat_goal": "Follow the cloaked man.",
    }
    formatted = format_turn_context(ctx)
    assert "Current beat goal: Follow the cloaked man." in formatted
```

**Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_build_turn_context_includes_current_beat_goal tests/test_dm_agent.py::test_format_turn_context_includes_beat_goal -v
```
Expected: FAIL

**Step 3: Update `build_turn_context()` in `spectator.py`**

Add a helper function near the top of `spectator.py` (after `_world_state_list`):

```python
def _get_current_beat_goal(world_state: dict) -> str:
    story_arc = world_state.get("story_arc") or {}
    current_beat = str(world_state.get("current_beat", "hook") or "hook")
    beat_data = story_arc.get(current_beat) or {}
    return str(beat_data.get("goal", "") or "")
```

In `build_turn_context()`, add `"current_beat_goal"` to the returned dict:

```python
return {
    # ... all existing keys ...
    "current_beat_goal": _get_current_beat_goal(world_state),
}
```

**Step 4: Update `format_turn_context()` in `spectator.py`**

In the `format_turn_context()` function, add a line for the beat goal after `"Phase goal:"`:

```python
f"Phase goal: {turn_context['phase_goal']}",
f"Current beat goal: {turn_context.get('current_beat_goal', '')}",
```

**Step 5: Run tests to verify they pass**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_build_turn_context_includes_current_beat_goal tests/test_dm_agent.py::test_format_turn_context_includes_beat_goal -v
```
Expected: PASS

**Step 6: Run full suite**

```bash
PYTHONPATH=. pytest -v
```
Expected: All tests pass.

**Step 7: Commit**

```bash
git add dnd/spectator.py tests/test_dm_agent.py
git commit -m "feat: add current beat goal to turn context"
```

---

### Task 6: Inject beat goal into the player agent's prompt

**Files:**
- Modify: `dnd/player_agent.py`
- Modify: `tests/test_player_agent.py`

**Step 1: Write the failing test**

First read `tests/test_player_agent.py` to understand existing patterns, then add:

```python
def test_generate_action_includes_beat_goal(monkeypatch, player_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    from dnd.character import CharacterSheet
    from dnd.player_agent import AutoPlayerAgent

    sheet = MagicMock()
    sheet.name = "Kraton"
    sheet.get_prompt_summary.return_value = "--- Character: Kraton (Sorcerer 1) ---"

    agent = AutoPlayerAgent(sheet)

    turn_context = {
        "actor_name": "Kraton",
        "actor_type": "player",
        "location": "Graysfall",
        "objective": "Follow the man.",
        "story_phase": "opening",
        "current_round": 1,
        "target_rounds": 10,
        "remaining_rounds": 9,
        "phase_goal": "Commit to the hook.",
        "scene_momentum": "steady",
        "immediate_danger": "None",
        "scene_summary": "The cloaked man is leaving.",
        "recent_party_actions": [],
        "last_progress_events": [],
        "resolved_events": [],
        "notable_npcs": [],
        "nearby_locations": [],
        "current_beat_goal": "Follow the cloaked man to discover where he is going.",
    }

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "Follow the cloaked man."}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.player_agent.requests.post", return_value=fake_response) as mock_post:
        agent.generate_action("The cloaked man is leaving.", [], turn_context=turn_context)

    prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "Follow the cloaked man to discover where he is going." in prompt
    assert "Current goal:" in prompt
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_player_agent.py::test_generate_action_includes_beat_goal -v
```
Expected: FAIL

**Step 3: Update `AutoPlayerAgent.generate_action()` in `player_agent.py`**

In the `generate_action()` method, add the beat goal block to the prompt. Find the prompt construction and add after the `context_block` line:

```python
beat_goal = (turn_context or {}).get("current_beat_goal", "")
beat_goal_line = f"Current goal: {beat_goal}\n" if beat_goal else ""

prompt = (
    "You are controlling the player character in spectator mode.\n"
    "Choose one short, concrete action that moves the scene forward.\n"
    "Respond in plain English only.\n"
    "Use ASCII characters only.\n"
    "Stay in character. Do not explain your reasoning. Do not write multiple options.\n"
    "Do not narrate outcomes, other speakers, or future turns.\n"
    "Do not include labels such as DM:, Assistant:, Outcome:, or your own name.\n\n"
    f"{beat_goal_line}"
    "Prefer actions that create progress: question, inspect, advance, rescue, confront, cast, strike, or seize evidence.\n"
    "Avoid repeating the same cautious movement unless immediate danger clearly forces it.\n"
    "When scene momentum is slow or stalled, do something that reveals information or forces a change.\n"
    "When only a few rounds remain, choose a decisive action instead of another setup action.\n\n"
    f"{self.player_sheet.get_prompt_summary()}\n"
    f"Turn context:\n{context_block}\n\n"
    "Recent party actions:\n"
    + ("\n".join(f"- {action}" for action in recent_party_actions[-3:]) if recent_party_actions else "- None recorded.")
)
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_player_agent.py::test_generate_action_includes_beat_goal -v
```
Expected: PASS

**Step 5: Run full suite**

```bash
PYTHONPATH=. pytest -v
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add dnd/player_agent.py tests/test_player_agent.py
git commit -m "feat: inject current beat goal into player agent prompt"
```

---

### Task 7: Wire up `generate_arc()` in `main.py` and smoke test

**Files:**
- Modify: `main.py`

**Step 1: Call `generate_arc()` after `generate_opening_scene()` in `main.py`**

Find this line in `main.py`:
```python
print(apply_base_style(highlight_quotes(wrap_text(dm.generate_opening_scene(player_sheet, npcs))), "parchment"))
```

Replace with:
```python
opening_scene = dm.generate_opening_scene(player_sheet, npcs)
dm.generate_arc(opening_scene)
print(apply_base_style(highlight_quotes(wrap_text(opening_scene)), "parchment"))
```

**Step 2: Run the full test suite one final time**

```bash
PYTHONPATH=. pytest -v
```
Expected: All tests pass.

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: call generate_arc after opening scene to establish story arc"
```

**Step 4: Manual smoke test**

Run the game in spectator mode with a short session (10 rounds) and verify:
1. "Generating story arc" thinking message appears after the opening scene
2. The player agent's first action relates to the opening hook (not a random distraction)
3. The story progresses through beats — watch for `current_beat` advancing in world state
4. The 10-round session reaches a more satisfying conclusion than before

```bash
python3 main.py
```
Choose: Spectator mode → 10 rounds → 1s autoplay → clone or create character → 2 companions

---

## Summary of Changes

| File | Change |
|------|--------|
| `dnd/dm/prompts.py` | Add `ARC_GENERATION_PROMPT`, `BEAT_EVALUATION_PROMPT` |
| `dnd/dm/agent.py` | Add `generate_arc()`, `_set_fallback_arc()`, `_evaluate_beat()`, `_current_beat_goal()`; modify `_dm_scene_context()` and `generate_response()`; remove `_update_story_progress()` |
| `dnd/spectator.py` | Add `_get_current_beat_goal()`; update `build_turn_context()` and `format_turn_context()` |
| `dnd/player_agent.py` | Inject `current_beat_goal` into prompt |
| `main.py` | Call `generate_arc()` after opening scene |
| `tests/test_dm_agent.py` | Add 9 new tests; remove 1 old hardcoded scenario test |
| `tests/test_player_agent.py` | Add 1 new test |
