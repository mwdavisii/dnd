# Scene Stalling & Companion Repetition Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix scene stalling (DM repeats same standoff for 5+ rounds) and companion repetition (same action every round) by using semantic stall detection via story summary and per-companion action tracking with fuzzy dedup.

**Architecture:** Stall detection shifts from raw scene summary token overlap to comparing OPEN THREADS sections from the rolling story summary. Companion repetition is fixed by tracking each companion's recent actions, injecting them into prompts with anti-repeat instructions, and replacing exact-match dedup with fuzzy token overlap (≥50%).

**Tech Stack:** Python, existing spectator/NPC agent modules, no new dependencies.

---

### Task 1: Add extract_open_threads() to spectator.py

**Files:**
- Modify: `dnd/spectator.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

In `tests/test_main.py`, add:

```python
from dnd.spectator import extract_open_threads

def test_extract_open_threads_parses_summary():
    summary = (
        "EVENTS SO FAR:\n"
        "- Party arrived in Ashford\n"
        "- Met Elric at the tavern\n\n"
        "OPEN THREADS:\n"
        "- Missing trader last seen near old mill\n"
        "- Hooded figure spotted at tavern\n\n"
        "ESCALATION LEVEL: Rising tension."
    )
    result = extract_open_threads(summary)
    assert "Missing trader" in result
    assert "Hooded figure" in result
    assert "EVENTS SO FAR" not in result
    assert "ESCALATION LEVEL" not in result


def test_extract_open_threads_returns_empty_on_missing_section():
    summary = "EVENTS SO FAR:\n- Something happened\n\nESCALATION LEVEL: Low."
    result = extract_open_threads(summary)
    assert result == ""
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_extract_open_threads_parses_summary tests/test_main.py::test_extract_open_threads_returns_empty_on_missing_section -v`
Expected: FAIL with ImportError

**Step 3: Implement**

In `dnd/spectator.py`, add this function (near `build_scene_memory`):

```python
def extract_open_threads(story_summary: str) -> str:
    """Extract the OPEN THREADS section from a rolling story summary."""
    if not story_summary or "OPEN THREADS" not in story_summary:
        return ""
    match = re.search(r"OPEN THREADS:\s*\n(.*?)(?:\n\n|\nESCALATION|\Z)", story_summary, re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip()
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_extract_open_threads_parses_summary tests/test_main.py::test_extract_open_threads_returns_empty_on_missing_section -v`
Expected: PASS

**Step 5: Commit**

```bash
git add dnd/spectator.py tests/test_main.py
git commit -m "feat: add extract_open_threads() for semantic stall detection"
```

---

### Task 2: Update detect_scene_stall() to use story summary threads

**Files:**
- Modify: `dnd/spectator.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing tests**

In `tests/test_main.py`, add:

```python
def test_detect_scene_stall_uses_open_threads_from_summary():
    # Scene summaries differ (below 55% overlap) but threads are identical
    stalled = detect_scene_stall(
        "Last turn: demand answers Consequences: The figure refuses.",
        "Last turn: threaten the figure Consequences: They hold their ground.",
        [],
        previous_threads="- Cloaked figure blocking the mill entrance",
        current_threads="- Cloaked figure blocking the mill entrance",
    )
    assert stalled is True


def test_detect_scene_stall_not_stalled_when_threads_change():
    stalled = detect_scene_stall(
        "Last turn: demand answers Consequences: The figure refuses.",
        "Last turn: push past the figure Consequences: You enter the mill.",
        [],
        previous_threads="- Cloaked figure blocking the mill entrance",
        current_threads="- Inside the mill, bandits spotted",
    )
    assert stalled is False


def test_detect_scene_stall_backward_compatible_without_threads():
    # Existing behavior works when threads are not provided
    stalled = detect_scene_stall(
        "Last turn: take a cautious step forward Consequences: The shadows stir near the clearing.",
        "Last turn: take another cautious step forward Consequences: The shadows stir near the clearing.",
        [],
    )
    assert stalled is True
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_detect_scene_stall_uses_open_threads_from_summary tests/test_main.py::test_detect_scene_stall_not_stalled_when_threads_change tests/test_main.py::test_detect_scene_stall_backward_compatible_without_threads -v`
Expected: FAIL (new params not accepted)

**Step 3: Implement**

Update `detect_scene_stall()` in `dnd/spectator.py`:

```python
def detect_scene_stall(
    previous_summary: str,
    new_summary: str,
    new_progress_events: list[str] | None = None,
    previous_threads: str = "",
    current_threads: str = "",
) -> bool:
    if new_progress_events:
        return False

    # Primary signal: compare open threads from story summary
    if previous_threads and current_threads:
        prev_tokens = set(_normalize_for_comparison(previous_threads).split())
        curr_tokens = set(_normalize_for_comparison(current_threads).split())
        if prev_tokens and curr_tokens:
            thread_overlap = len(prev_tokens & curr_tokens) / max(len(prev_tokens | curr_tokens), 1)
            if thread_overlap >= 0.70:
                return True

    # Fallback: existing scene summary overlap check
    previous = _normalize_for_comparison(previous_summary)
    current = _normalize_for_comparison(new_summary)
    if not previous or not current:
        return False
    previous_tokens = set(previous.split())
    current_tokens = set(current.split())
    if not previous_tokens or not current_tokens:
        return False
    overlap = len(previous_tokens & current_tokens) / max(len(previous_tokens | current_tokens), 1)
    return overlap >= 0.55
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_main.py -k "detect_scene_stall" -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dnd/spectator.py tests/test_main.py
git commit -m "feat: semantic stall detection via story summary open threads"
```

---

### Task 3: Wire thread-based stall detection into process_dm_turn()

**Files:**
- Modify: `main.py`
- Modify: `dnd/spectator.py` (import)
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

In `tests/test_main.py`, add:

```python
def test_process_dm_turn_passes_threads_to_stall_detection(monkeypatch):
    from unittest.mock import MagicMock, patch, call
    import main as main_module

    fake_dm = MagicMock()
    fake_dm.generate_response.return_value = (
        "The figure blocks your path again.",
        "The figure blocks your path again.",
    )
    fake_dm.world_state = {
        "scene_summary": "Previous scene.",
        "recent_party_actions": [],
        "last_progress_events": [],
        "reward_history": [],
        "scene_stall_count": 0,
        "story_summary": (
            "EVENTS SO FAR:\n- Arrived at mill\n\n"
            "OPEN THREADS:\n- Cloaked figure blocking entrance\n\n"
            "ESCALATION LEVEL: Medium."
        ),
        "previous_open_threads": "- Cloaked figure blocking entrance",
    }
    fake_dm.story_is_complete.return_value = False

    fake_player = MagicMock()
    fake_player.name = "Kraton"

    fake_handler = MagicMock()

    captured_stall_args = {}

    original_detect = main_module.detect_scene_stall

    def spy_detect(*args, **kwargs):
        captured_stall_args.update(kwargs)
        return original_detect(*args, **kwargs)

    monkeypatch.setattr(main_module, "build_scene_memory", lambda *_args, **_kwargs: "scene")
    monkeypatch.setattr(main_module, "detect_scene_stall", spy_detect)

    main_module.process_dm_turn("Step aside.", fake_dm, {}, fake_player, {}, fake_handler)

    assert "current_threads" in captured_stall_args or "previous_threads" in captured_stall_args
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_process_dm_turn_passes_threads_to_stall_detection -v`
Expected: FAIL

**Step 3: Implement**

In `main.py`, update the import to include `extract_open_threads`:

Find:
```python
from dnd.spectator import build_scene_memory, build_turn_context, detect_scene_stall, is_fallback_action, _strip_fallback_marker
```
Change to:
```python
from dnd.spectator import build_scene_memory, build_turn_context, detect_scene_stall, extract_open_threads, is_fallback_action, _strip_fallback_marker
```

In `process_dm_turn()`, update the stall detection block. Find (around lines 316-321):
```python
    new_progress_events = dm.world_state.get("last_progress_events", [])
    scene_stall_count = int(dm.world_state.get("scene_stall_count", 0) or 0)
    if detect_scene_stall(previous_scene_memory, scene_memory, new_progress_events):
        scene_stall_count += 1
    else:
        scene_stall_count = 0
    dm.update_world_state("scene_stall_count", scene_stall_count)
```

Replace with:
```python
    new_progress_events = dm.world_state.get("last_progress_events", [])
    scene_stall_count = int(dm.world_state.get("scene_stall_count", 0) or 0)
    previous_threads = str(dm.world_state.get("previous_open_threads", "") or "")
    current_threads = extract_open_threads(str(dm.world_state.get("story_summary", "") or ""))
    if detect_scene_stall(
        previous_scene_memory, scene_memory, new_progress_events,
        previous_threads=previous_threads, current_threads=current_threads,
    ):
        scene_stall_count += 1
    else:
        scene_stall_count = 0
    dm.update_world_state("scene_stall_count", scene_stall_count)
    dm.update_world_state("previous_open_threads", current_threads)
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_main.py -v -k "not ollama"`
Expected: All PASS

**Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: wire thread-based stall detection into process_dm_turn"
```

---

### Task 4: Add fuzzy duplicate detection to validate_turn_output()

**Files:**
- Modify: `dnd/spectator.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing tests**

In `tests/test_main.py`, add:

```python
def test_validate_turn_output_rejects_fuzzy_duplicate():
    from dnd.spectator import is_fallback_action

    action = validate_turn_output(
        "I raise my shield and stand firm, blocking the path.",
        actor_name="Garrick",
        actor_type="companion",
        recent_party_actions=["Garrick acted: I raise my shield, standing firm to block the path."],
    )
    assert is_fallback_action(action)


def test_validate_turn_output_allows_genuinely_different_action():
    from dnd.spectator import is_fallback_action

    action = validate_turn_output(
        "I slip behind the figure and search for a back entrance to the mill.",
        actor_name="Lyra",
        actor_type="companion",
        recent_party_actions=["Garrick acted: I raise my shield, standing firm to block the path."],
    )
    assert not is_fallback_action(action)
    assert "slip behind" in action.lower()
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_validate_turn_output_rejects_fuzzy_duplicate tests/test_main.py::test_validate_turn_output_allows_genuinely_different_action -v`
Expected: First test FAILS (fuzzy duplicate passes through), second PASSES

**Step 3: Implement**

In `dnd/spectator.py`, add a helper function:

```python
def _fuzzy_duplicate(action: str, recent_actions: list[str], threshold: float = 0.50) -> bool:
    """Return True if action shares >= threshold token overlap with any recent action."""
    action_tokens = set(_normalize_for_comparison(action).split())
    if not action_tokens:
        return False
    for recent in recent_actions:
        recent_text = recent.split(" acted: ", 1)[-1] if " acted: " in recent else recent
        recent_tokens = set(_normalize_for_comparison(recent_text).split())
        if not recent_tokens:
            continue
        overlap = len(action_tokens & recent_tokens) / max(len(action_tokens | recent_tokens), 1)
        if overlap >= threshold:
            return True
    return False
```

In `validate_turn_output()`, replace the exact-match duplicate check (lines 147-152):

Find:
```python
    normalized_recent = {
        _normalize_for_comparison(entry.split(" acted: ", 1)[-1])
        for entry in (recent_party_actions or [])[-3:]
    }
    if _normalize_for_comparison(cleaned) in normalized_recent:
        return fallback or suggest_objective_action(actor_name, actor_type, turn_context)
```

Replace with:
```python
    if _fuzzy_duplicate(cleaned, list(recent_party_actions or [])[-3:]):
        return fallback or suggest_objective_action(actor_name, actor_type, turn_context)
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_main.py -k "validate_turn_output" -v`
Expected: All PASS

**Step 5: Run full test suite to check for regressions**

Run: `PYTHONPATH=. pytest -v -k "not ollama"`
Expected: All PASS

**Step 6: Commit**

```bash
git add dnd/spectator.py tests/test_main.py
git commit -m "feat: fuzzy duplicate detection for companion actions"
```

---

### Task 5: Add per-companion action tracking and anti-repeat prompt

**Files:**
- Modify: `dnd/npc/agent.py`
- Test: `tests/test_npc_agent.py`

**Step 1: Write the failing tests**

In `tests/test_npc_agent.py`, add:

```python
def test_npc_tracks_own_recent_actions(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "I scout the eastern perimeter."}

    with patch("dnd.npc.agent.requests.post", return_value=fake_response):
        agent.generate_turn_action([], "The scene is tense.")

    assert len(agent.recent_actions) == 1
    assert "scout" in agent.recent_actions[0].lower()


def test_npc_recent_actions_capped_at_three(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)
    agent.recent_actions = ["action one", "action two", "action three"]

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "I check the back entrance."}

    with patch("dnd.npc.agent.requests.post", return_value=fake_response):
        agent.generate_turn_action([], "The scene continues.")

    assert len(agent.recent_actions) == 3
    assert "action one" not in agent.recent_actions
    assert "check the back entrance" in agent.recent_actions[-1].lower()


def test_npc_prompt_includes_own_recent_actions(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)
    agent.recent_actions = ["I raise my shield.", "I move to flank the enemy."]

    captured = {}
    def fake_post(_url, json=None, timeout=None):
        captured["prompt"] = json["prompt"]
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "I search for a hidden passage."}
        return response

    with patch("dnd.npc.agent.requests.post", side_effect=fake_post):
        agent.generate_turn_action([], "The hallway is dark.")

    assert "Your recent actions (do NOT repeat these)" in captured["prompt"]
    assert "I raise my shield." in captured["prompt"]
    assert "I move to flank the enemy." in captured["prompt"]
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_npc_agent.py::test_npc_tracks_own_recent_actions tests/test_npc_agent.py::test_npc_recent_actions_capped_at_three tests/test_npc_agent.py::test_npc_prompt_includes_own_recent_actions -v`
Expected: FAIL

**Step 3: Implement**

In `dnd/npc/agent.py`:

1. In `__init__`, add after `self.memory = ...` (around line 21):
```python
self.recent_actions = []
```

2. Add a helper method:
```python
def _format_own_recent_actions(self) -> str:
    if not self.recent_actions:
        return ""
    lines = "\n".join(f"- {action}" for action in self.recent_actions)
    return (
        "Your recent actions (do NOT repeat these):\n"
        f"{lines}\n"
        "You MUST do something DIFFERENT from the above.\n"
    )
```

3. In `generate_turn_action()`, inject own recent actions into the prompt. Find the line:
```python
            f"It is {self.name}'s turn.\n"
```
Add BEFORE it:
```python
            f"{self._format_own_recent_actions()}\n"
```

4. In `generate_turn_action()`, after the fallback marker is stripped and before the return (around line 132), add the action to `recent_actions`. Find:
```python
            final_response = _strip_fallback_marker(final_response)
            if final_response:
                self.history.append({"role": "assistant", "content": final_response})
                self.remember(f"{self.name} took a turn: {final_response}")
            return final_response
```

Change to:
```python
            final_response = _strip_fallback_marker(final_response)
            if final_response:
                self.history.append({"role": "assistant", "content": final_response})
                self.remember(f"{self.name} took a turn: {final_response}")
                self.recent_actions.append(final_response)
                self.recent_actions = self.recent_actions[-3:]
            return final_response
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_npc_agent.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dnd/npc/agent.py tests/test_npc_agent.py
git commit -m "feat: per-companion action tracking with anti-repeat prompt"
```

---

### Task 6: Full test suite verification

**Files:**
- Test: all test files

**Step 1: Run full test suite**

Run: `PYTHONPATH=. pytest -v -k "not ollama"`
Expected: All PASS

**Step 2: Verify no regressions in existing stall detection tests**

Run: `PYTHONPATH=. pytest tests/test_main.py -k "detect_scene_stall" -v`
Expected: All PASS (old and new tests)

**Step 3: Commit any fixups if needed**

Only if tests reveal issues. Otherwise, no commit needed.
