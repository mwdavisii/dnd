# Context Chaining: Rolling Story Summary — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a rolling story summary that persists across rounds so the DM, player agent, and NPC agents maintain narrative coherence throughout a full adventure arc.

**Architecture:** After each DM response, a new non-streaming LLM call condenses the previous summary + latest turn into a structured summary (events, open threads, escalation level). This summary is stored in `world_state["story_summary"]` and injected into all agent prompts. The existing `scene_summary` (last-turn snapshot) is kept for stall detection.

**Tech Stack:** Python, Ollama REST API, SQLite (existing world_state persistence)

---

### Task 1: Add STORY_SUMMARY_PROMPT to prompts.py

**Files:**
- Modify: `dnd/dm/prompts.py` (append after BEAT_EVALUATION_PROMPT)
- Test: `tests/test_dm_agent.py`

**Step 1: Write the failing test**

In `tests/test_dm_agent.py`, add:

```python
def test_story_summary_prompt_exists():
    from dnd.dm.prompts import STORY_SUMMARY_PROMPT
    assert "EVENTS SO FAR" in STORY_SUMMARY_PROMPT
    assert "OPEN THREADS" in STORY_SUMMARY_PROMPT
    assert "ESCALATION LEVEL" in STORY_SUMMARY_PROMPT
    assert "{previous_summary}" in STORY_SUMMARY_PROMPT
    assert "{player_action}" in STORY_SUMMARY_PROMPT
    assert "{dm_response}" in STORY_SUMMARY_PROMPT
    assert "{current_beat}" in STORY_SUMMARY_PROMPT
    assert "{beat_goal}" in STORY_SUMMARY_PROMPT
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_story_summary_prompt_exists -v`
Expected: FAIL with ImportError

**Step 3: Write the prompt**

At the end of `dnd/dm/prompts.py`, add:

```python
STORY_SUMMARY_PROMPT = """
You are a story editor tracking the narrative of a D&D adventure.

Previous story summary:
{previous_summary}

Current story beat: {current_beat} — {beat_goal}

What just happened:
Player action: {player_action}
DM response: {dm_response}

Update the story summary. Follow this exact format:

EVENTS SO FAR:
- (chronological bullet points of key plot beats only — no minor actions)

OPEN THREADS:
- (things introduced but not yet resolved — NPCs, clues, threats, mysteries)

ESCALATION LEVEL: (one sentence — the current tension/stakes)

Rules:
- Do not repeat events already listed — only add genuinely new developments
- Remove threads that were conclusively resolved this turn
- Keep EVENTS to 8 bullets max — merge older minor beats if needed
- Keep OPEN THREADS to 5 items max
- Total output must be under 400 words
- Output ONLY the summary in the format above — no explanation, no commentary
"""
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_story_summary_prompt_exists -v`
Expected: PASS

**Step 5: Commit**

```bash
git add dnd/dm/prompts.py tests/test_dm_agent.py
git commit -m "feat: add STORY_SUMMARY_PROMPT for rolling context chain"
```

---

### Task 2: Add _update_story_summary() method to DungeonMaster

**Files:**
- Modify: `dnd/dm/agent.py` (add import of STORY_SUMMARY_PROMPT, add method)
- Test: `tests/test_dm_agent.py`

**Step 1: Write the failing tests**

In `tests/test_dm_agent.py`, add:

```python
def test_update_story_summary_calls_llm_and_stores_result(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("story_arc", {
        "hook": {"goal": "Follow the cloaked man.", "key_npcs": [], "success_condition": "Party confronts him."},
    })

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "response": (
            "EVENTS SO FAR:\n"
            "- Party arrived in Ashford and received a sealed letter\n\n"
            "OPEN THREADS:\n"
            "- Sealed letter contents unknown\n\n"
            "ESCALATION LEVEL: Low tension. Party is investigating an initial lead."
        )
    }
    fake_response.raise_for_status.return_value = None

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        dm._update_story_summary("Open the letter.", "You break the seal and find a warning about raiders.")

    assert "Party arrived in Ashford" in dm.world_state["story_summary"]
    assert "OPEN THREADS" in dm.world_state["story_summary"]


def test_update_story_summary_handles_network_error(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("story_summary", "Previous summary content.")

    with patch("dnd.dm.agent.requests.post", side_effect=requests.exceptions.RequestException("boom")):
        dm._update_story_summary("Do something.", "Something happens.")

    # Should keep the previous summary on error
    assert dm.world_state["story_summary"] == "Previous summary content."


def test_update_story_summary_seeds_initial_summary(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    # No story_summary set yet — should use "No prior summary."
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("story_arc", {
        "hook": {"goal": "Investigate.", "key_npcs": [], "success_condition": "Clue found."},
    })

    captured = {}
    def fake_post(_url, json=None, timeout=None):
        captured["prompt"] = json["prompt"]
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "EVENTS SO FAR:\n- Initial event\n\nOPEN THREADS:\n- Thread one\n\nESCALATION LEVEL: Low."}
        return response

    with patch("dnd.dm.agent.requests.post", side_effect=fake_post):
        dm._update_story_summary("Look around.", "You see a village square.")

    assert "No prior summary" in captured["prompt"]
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_update_story_summary_calls_llm_and_stores_result tests/test_dm_agent.py::test_update_story_summary_handles_network_error tests/test_dm_agent.py::test_update_story_summary_seeds_initial_summary -v`
Expected: FAIL with AttributeError

**Step 3: Implement _update_story_summary()**

In `dnd/dm/agent.py`:

1. Add `STORY_SUMMARY_PROMPT` to the import line (line 8):
```python
from dnd.dm.prompts import ARC_GENERATION_PROMPT, BEAT_EVALUATION_PROMPT, OPENING_SCENE_PROMPT, STORY_SUMMARY_PROMPT, SYSTEM_PROMPT
```

2. Add the method to the `DungeonMaster` class, after `_evaluate_beat()`:

```python
def _update_story_summary(self, player_action: str, dm_response: str) -> None:
    """Update the rolling story summary with the latest turn's events."""
    previous_summary = str(self.world_state.get("story_summary", "") or "").strip()
    if not previous_summary:
        previous_summary = "No prior summary. This is the first update."

    story_arc = self.world_state.get("story_arc") or {}
    current_beat = str(self.world_state.get("current_beat", "hook") or "hook")
    beat_goal = str(story_arc.get(current_beat, {}).get("goal", "") or "")

    prompt = STORY_SUMMARY_PROMPT.format(
        previous_summary=previous_summary,
        current_beat=current_beat,
        beat_goal=beat_goal,
        player_action=player_action[:200],
        dm_response=dm_response[:800],
    )

    try:
        _t0 = time.time()
        response = requests.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=(5, 60),
        )
        response.raise_for_status()
        print(style(f"[Summary: {time.time() - _t0:.1f}s]", "gray", dim=True))
        raw = response.json().get("response", "").strip()
        if raw and "EVENTS SO FAR" in raw:
            self.update_world_state("story_summary", raw)
    except requests.exceptions.RequestException:
        pass  # Keep previous summary on error
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_update_story_summary_calls_llm_and_stores_result tests/test_dm_agent.py::test_update_story_summary_handles_network_error tests/test_dm_agent.py::test_update_story_summary_seeds_initial_summary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: add _update_story_summary() method to DungeonMaster"
```

---

### Task 3: Wire _update_story_summary() into generate_response()

**Files:**
- Modify: `dnd/dm/agent.py` (in `generate_response()`, call `_update_story_summary()` after `_evaluate_beat()`)
- Test: `tests/test_dm_agent.py`

**Step 1: Write the failing test**

In `tests/test_dm_agent.py`, add:

```python
def test_generate_response_calls_update_story_summary(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.iter_lines.return_value = [
        b'{"response":"The trail bends toward the ruins.","done":false}',
        b'{"done":true}',
    ]

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        with patch.object(dm, "_evaluate_beat"):
            with patch.object(dm, "_update_story_summary") as mock_update:
                dm.generate_response("Follow the trail.", player_sheet, {})

    mock_update.assert_called_once()
    args = mock_update.call_args[0]
    assert args[0] == "Follow the trail."  # player_action
    assert "trail" in args[1].lower() or "ruins" in args[1].lower()  # dm_response
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_calls_update_story_summary -v`
Expected: FAIL — `_update_story_summary` never called

**Step 3: Wire the call in generate_response()**

In `dnd/dm/agent.py`, inside `generate_response()`, after line 298 (`self._evaluate_beat(cleaned_response)`), add:

```python
            self._update_story_summary(prompt, cleaned_response)
```

Note: `prompt` here is the user's submitted action (the first parameter to `generate_response()`), not `full_prompt`.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_calls_update_story_summary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: wire _update_story_summary into generate_response loop"
```

---

### Task 4: Integrate story_summary into the DM prompt

**Files:**
- Modify: `dnd/dm/agent.py` (in `generate_response()`, add story summary to prompt; add `_get_story_summary()` helper)
- Test: `tests/test_dm_agent.py`

**Step 1: Write the failing test**

In `tests/test_dm_agent.py`, add:

```python
def test_generate_response_includes_story_summary_in_prompt(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("story_summary", (
        "EVENTS SO FAR:\n"
        "- Party arrived in Ashford\n\n"
        "OPEN THREADS:\n"
        "- Sealed letter\n\n"
        "ESCALATION LEVEL: Low tension."
    ))
    dm.update_world_state("target_rounds", 10)
    dm.update_world_state("remaining_rounds", 8)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.iter_lines.return_value = [
        b'{"response":"The trail bends.","done":false}',
        b'{"done":true}',
    ]

    with patch("dnd.dm.agent.requests.post", return_value=fake_response) as mock_post:
        with patch.object(dm, "_evaluate_beat"):
            with patch.object(dm, "_update_story_summary"):
                dm.generate_response("Look around.", player_sheet, {})

    prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "Story so far:" in prompt
    assert "Party arrived in Ashford" in prompt
    assert "OPEN THREADS" in prompt
    assert "Last turn:" in prompt
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_includes_story_summary_in_prompt -v`
Expected: FAIL — "Story so far:" not in prompt

**Step 3: Implement**

Add a helper method to `DungeonMaster`:

```python
def _get_story_summary(self) -> str:
    """Return the rolling story summary, or a placeholder if none exists yet."""
    summary = str(self.world_state.get("story_summary", "") or "").strip()
    if not summary:
        return "No story summary yet — this is the beginning of the adventure."
    return summary
```

In `generate_response()`, change the prompt construction (lines 258-260) from:

```python
            "Recent story beats:\n"
            f"{self._recent_history_summary()}\n\n"
```

To:

```python
            "Story so far:\n"
            f"{self._get_story_summary()}\n\n"
            "Last turn:\n"
            f"{self._recent_history_summary(max_entries=3)}\n\n"
```

Update `_recent_history_summary()` to accept an optional `max_entries` parameter:

```python
def _recent_history_summary(self, max_entries: int = 6) -> str:
    if not self.history:
        return "- No prior events recorded."
    summary_lines = []
    for entry in self.history[-max_entries:]:
        role = entry.get("role", "assistant").title()
        content = " ".join(str(entry.get("content", "")).split())
        if len(content) > 140:
            content = content[:137].rstrip() + "..."
        summary_lines.append(f"- {role}: {content}")
    return "\n".join(summary_lines)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_includes_story_summary_in_prompt -v`
Expected: PASS

**Step 5: Run full test suite to check for regressions**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: inject rolling story summary into DM prompt"
```

---

### Task 5: Feed story_summary to NPC and player agents

**Files:**
- Modify: `dnd/npc/agent.py` (add story_summary to `generate_turn_action()` prompt)
- Modify: `dnd/spectator.py` (add `story_summary` field to `build_turn_context()` output)
- Modify: `main.py` (pass `story_summary` when calling `run_spectator_turn`)
- Test: `tests/test_npc_agent.py`, `tests/test_main.py`

**Step 1: Write the failing tests**

In `tests/test_npc_agent.py`, add:

```python
def test_npc_turn_prompt_includes_story_summary(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)

    captured = {}
    def fake_post(_url, json=None, timeout=None):
        captured["prompt"] = json["prompt"]
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "I scout the perimeter."}
        return response

    turn_context = {
        "actor_name": "Aria",
        "actor_type": "companion",
        "location": "Ashford",
        "objective": "Investigate the mine.",
        "story_phase": "midgame",
        "current_round": 5,
        "target_rounds": 15,
        "remaining_rounds": 10,
        "phase_goal": "Escalate.",
        "scene_momentum": "steady",
        "immediate_danger": "None",
        "scene_summary": "The mine entrance is dark.",
        "recent_party_actions": [],
        "last_progress_events": [],
        "resolved_events": [],
        "notable_npcs": [],
        "nearby_locations": [],
        "current_beat_goal": "Enter the mine.",
        "story_summary": "EVENTS SO FAR:\n- Party arrived at Ashford\n\nOPEN THREADS:\n- Mine entrance\n\nESCALATION LEVEL: Medium.",
    }

    with patch("dnd.npc.agent.requests.post", side_effect=fake_post):
        agent.generate_turn_action(
            game_context=[],
            scene_summary="The mine entrance is dark.",
            recent_party_actions=[],
            turn_context=turn_context,
        )

    assert "EVENTS SO FAR" in captured["prompt"]
    assert "Party arrived at Ashford" in captured["prompt"]
```

In `tests/test_main.py`, add:

```python
def test_build_turn_context_includes_story_summary():
    context = build_turn_context(
        {
            "location": "Ashford",
            "objective": "Investigate.",
            "story_phase": "opening",
            "current_round": 1,
            "target_rounds": 10,
            "remaining_rounds": 9,
            "story_summary": "EVENTS SO FAR:\n- Arrived in Ashford\n\nOPEN THREADS:\n- Letter\n\nESCALATION LEVEL: Low.",
        },
        actor_name="Kraton",
        actor_type="player",
        scene_summary="The square is quiet.",
    )
    assert context["story_summary"] == "EVENTS SO FAR:\n- Arrived in Ashford\n\nOPEN THREADS:\n- Letter\n\nESCALATION LEVEL: Low."
```

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_npc_agent.py::test_npc_turn_prompt_includes_story_summary tests/test_main.py::test_build_turn_context_includes_story_summary -v`
Expected: FAIL

**Step 3: Implement**

In `dnd/spectator.py`, in `build_turn_context()`, add to the returned dict (after `"current_beat_goal"`):

```python
"story_summary": str(world_state.get("story_summary", "") or ""),
```

In `dnd/spectator.py`, in `format_turn_context()`, add a line to the output (after the `current_beat_goal` line):

```python
f"Story summary: {turn_context.get('story_summary', 'No summary yet.')}",
```

In `dnd/npc/agent.py`, in `generate_turn_action()`, add the story summary to the prompt. After the line `f"{context_block}\n\n"` (line 98), add:

```python
"Story so far:\n"
f"{self._get_story_summary(turn_context)}\n\n"
```

Add a helper method to `NPCAgent`:

```python
def _get_story_summary(self, turn_context: dict | None = None) -> str:
    if turn_context:
        summary = str(turn_context.get("story_summary", "") or "").strip()
        if summary:
            return summary
    return "No story summary available yet."
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_npc_agent.py::test_npc_turn_prompt_includes_story_summary tests/test_main.py::test_build_turn_context_includes_story_summary -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All PASS (except ollama-dependent tests which are skipped)

**Step 6: Commit**

```bash
git add dnd/spectator.py dnd/npc/agent.py tests/test_npc_agent.py tests/test_main.py
git commit -m "feat: feed rolling story summary to NPC and player agents"
```

---

### Task 6: Final integration test and cleanup

**Files:**
- Test: `tests/test_dm_agent.py`

**Step 1: Write an integration-style test**

In `tests/test_dm_agent.py`, add a test that simulates multiple rounds and verifies the summary accumulates:

```python
def test_story_summary_accumulates_across_rounds(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("current_beat", "hook")
    dm.update_world_state("story_arc", {
        "hook": {"goal": "Investigate.", "key_npcs": [], "success_condition": "Clue found."},
        "complication": {"goal": "Escape.", "key_npcs": [], "success_condition": "Party escapes."},
    })

    round_1_summary = (
        "EVENTS SO FAR:\n- Party arrived in Ashford\n\n"
        "OPEN THREADS:\n- Sealed letter\n\n"
        "ESCALATION LEVEL: Low tension."
    )
    round_2_summary = (
        "EVENTS SO FAR:\n- Party arrived in Ashford\n- Opened the letter, found raider warning\n\n"
        "OPEN THREADS:\n- Raider threat from the north\n\n"
        "ESCALATION LEVEL: Rising tension. Raiders confirmed nearby."
    )

    call_count = [0]
    def fake_post(_url, json=None, **kwargs):
        response = MagicMock()
        response.raise_for_status.return_value = None
        if "Story so far" not in str(json.get("prompt", "")) and "EVENTS SO FAR" not in str(json.get("prompt", "")):
            # This is a generate_response call (streaming)
            response.iter_lines.return_value = [
                b'{"response":"Something happens.","done":false}',
                b'{"done":true}',
            ]
        else:
            # This is a summary update call
            call_count[0] += 1
            if call_count[0] == 1:
                response.json.return_value = {"response": round_1_summary}
            else:
                response.json.return_value = {"response": round_2_summary}
        return response

    with patch("dnd.dm.agent.requests.post", side_effect=fake_post):
        with patch.object(dm, "_evaluate_beat"):
            dm.generate_response("Look around.", player_sheet, {})
            assert "Party arrived in Ashford" in dm.world_state.get("story_summary", "")

            dm.generate_response("Open the letter.", player_sheet, {})
            assert "raider warning" in dm.world_state.get("story_summary", "").lower()
            assert "Rising tension" in dm.world_state.get("story_summary", "")
```

**Step 2: Run test**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_story_summary_accumulates_across_rounds -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/test_dm_agent.py
git commit -m "test: add multi-round story summary accumulation test"
```
