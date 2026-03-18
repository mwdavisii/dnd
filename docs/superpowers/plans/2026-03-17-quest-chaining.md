# Quest Chaining System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-round game termination with a quest-chaining system that flows epilogue → campaign summary → downtime narration → level up / rest / shop → new quest, preserving narrative continuity across quests.

**Architecture:** On quest completion, `DungeonMaster` compresses the story into a `campaign_summary` (~300 words) stored in `campaign_history`. Operational world state is reset; characters, NPCs, locations, and resolved events carry forward. A `run_post_quest_flow()` helper in `main.py` orchestrates the full transition and replaces both existing break-out-of-loop completion paths.

**Tech Stack:** Python 3, SQLite (via existing `save_world_state`/`load_world_state`), Ollama HTTP API (existing `requests.post` pattern), pytest + `unittest.mock`

---

## File Map

| File | Change |
|------|--------|
| `dnd/data.py` | Add `MAX_LEVEL = 20` constant |
| `dnd/character.py` | Add `learn_spell()` method |
| `dnd/dm/prompts.py` | Add `{campaign_context}` slot to `ARC_GENERATION_PROMPT`; add `CAMPAIGN_SUMMARY_PROMPT`, `DOWNTIME_SCENE_PROMPT` |
| `dnd/dm/agent.py` | Add `generate_campaign_summary()`, `generate_downtime_scene()`, `reset_for_new_quest()`; extend `generate_arc()` and `generate_opening_scene()` with optional `campaign_context` param |
| `main.py` | Add `run_level_up_menu()`, `run_between_quest_menu()`, `run_post_quest_flow()`; replace both completion break paths with calls to `run_post_quest_flow()` |
| `tests/test_character.py` | New test for `learn_spell()` |
| `tests/test_dm_agent.py` | New tests for all three new DM methods; regression tests for `generate_arc` / `generate_opening_scene` |
| `tests/test_main.py` | New tests for `run_level_up_menu`, `run_between_quest_menu`, `run_post_quest_flow` |

---

## Task 1: Add `MAX_LEVEL` constant, `learn_spell()`, and new prompts

**Files:**
- Modify: `dnd/data.py`
- Modify: `dnd/character.py`
- Modify: `dnd/dm/prompts.py`
- Test: `tests/test_character.py`

- [ ] **Step 1: Add `MAX_LEVEL` to `dnd/data.py`**

Add after the `_BEAT_PHASE` dict (line 64):

```python
MAX_LEVEL = 20  # D&D 5e level cap
```

- [ ] **Step 2: Write failing test for `learn_spell()`**

Add to `tests/test_character.py` (use the existing `character_db` fixture pattern — look for how other tests set up a character):

```python
def test_learn_spell_adds_spell_to_character(character_db):
    from dnd.character import CharacterSheet
    sheet = CharacterSheet(name=character_db["player_name"])
    initial_spell_count = len(sheet.spells)

    sheet.learn_spell("Thunderwave")

    sheet.refresh_cache()
    spell_names = [s["name"] for s in sheet.spells]
    assert "Thunderwave" in spell_names
    assert len(sheet.spells) == initial_spell_count + 1


def test_learn_spell_does_not_add_duplicate(character_db):
    from dnd.character import CharacterSheet
    sheet = CharacterSheet(name=character_db["player_name"])
    sheet.learn_spell("Thunderwave")
    sheet.refresh_cache()
    count_after_first = len(sheet.spells)

    sheet.learn_spell("Thunderwave")
    sheet.refresh_cache()
    assert len(sheet.spells) == count_after_first


def test_learn_spell_ignores_unknown_spell(character_db):
    from dnd.character import CharacterSheet
    sheet = CharacterSheet(name=character_db["player_name"])
    count = len(sheet.spells)

    sheet.learn_spell("FluxCapacitor")  # not in spells table

    sheet.refresh_cache()
    assert len(sheet.spells) == count  # no change
```

- [ ] **Step 3: Run tests to confirm they fail**

Run: `PYTHONPATH=. pytest tests/test_character.py::test_learn_spell_adds_spell_to_character -v`
Expected: FAIL with `AttributeError: 'CharacterSheet' object has no attribute 'learn_spell'`

- [ ] **Step 4: Implement `learn_spell()` in `dnd/character.py`**

Add after the `level_up()` method (around line 456):

```python
def learn_spell(self, spell_name: str) -> None:
    """Add a spell to this character by name. No-ops for unknown spells or duplicates."""
    conn = get_db_connection()
    spell_row = conn.execute("SELECT id FROM spells WHERE name = ?", (spell_name,)).fetchone()
    if spell_row is None:
        conn.close()
        return
    already_known = conn.execute(
        "SELECT 1 FROM character_spells WHERE character_id = ? AND spell_id = ?",
        (self._id, spell_row["id"]),
    ).fetchone()
    if already_known is None:
        conn.execute(
            "INSERT INTO character_spells (character_id, spell_id) VALUES (?, ?)",
            (self._id, spell_row["id"]),
        )
        conn.commit()
    conn.close()
    self.refresh_cache()
```

- [ ] **Step 5: Run tests to confirm they pass**

Run: `PYTHONPATH=. pytest tests/test_character.py -v`
Expected: All PASS

- [ ] **Step 6: Add `{campaign_context}` slot to `ARC_GENERATION_PROMPT` and fix call site atomically**

**In `dnd/dm/prompts.py`**, replace the start of `ARC_GENERATION_PROMPT`:

```python
ARC_GENERATION_PROMPT = """
{campaign_context}
You are analyzing the opening scene of a D&D adventure to create a structured story arc.
```

**In `dnd/dm/agent.py`**, update the `generate_arc()` call site (line 97) at the same time — both changes go in one commit to prevent a `KeyError` window:

```python
# Change signature to accept campaign_context (default empty = first quest)
def generate_arc(self, opening_scene: str, campaign_context: str = "") -> None:
    ...
    prompt = ARC_GENERATION_PROMPT.format(
        opening_scene=opening_scene,
        campaign_context=f"Previous quest summary:\n{campaign_context}\n\n" if campaign_context else "",
    )
```

- [ ] **Step 7: Add `CAMPAIGN_SUMMARY_PROMPT` to `dnd/dm/prompts.py`**

Append at end of file:

```python
CAMPAIGN_SUMMARY_PROMPT = """
You are summarizing a completed D&D adventure for the campaign record.

Story summary:
{story_summary}

Resolved events:
{resolved_events}

Notable NPCs encountered:
{notable_npcs}

Story ending type: {ending_type}
Resolution goal: {resolution_goal}

Write a single prose paragraph of approximately 300 words that covers:
- What the party set out to do and why
- The key obstacles and turning points they faced
- Which NPCs were important and how they featured
- How the story ended and what was definitively resolved
- Any threads that were left open or unresolved

Write only the summary paragraph. No labels, headers, or commentary.
"""
```

- [ ] **Step 8: Add `DOWNTIME_SCENE_PROMPT` to `dnd/dm/prompts.py`**

Append after `CAMPAIGN_SUMMARY_PROMPT`:

```python
DOWNTIME_SCENE_PROMPT = """
You are narrating a brief downtime scene between two D&D adventures.

What just happened:
{campaign_summary}

Ending type: {ending_type}
Character name: {player_name}

Write 2-3 short paragraphs narrating the recovery period between adventures:
- Where the party rests and what the world looks like after the previous quest
- A sense of time passing — days or weeks, not hours
- A hint of what lies ahead without revealing the new quest

Do not introduce new named characters or specific new threats.
Do not ask what the player does next.
Keep it under 150 words.
Write only the narration. No labels.
"""
```

- [ ] **Step 9: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All PASS (the `generate_arc()` signature change is backward-compatible — `campaign_context` defaults to `""`)

- [ ] **Step 10: Commit**

```bash
git add dnd/data.py dnd/character.py dnd/dm/prompts.py dnd/dm/agent.py tests/test_character.py
git commit -m "feat: add MAX_LEVEL, learn_spell, quest-chaining prompts, and extend generate_arc"
```

---

## Task 2: Implement `reset_for_new_quest()` on `DungeonMaster`

**Files:**
- Modify: `dnd/dm/agent.py`
- Test: `tests/test_dm_agent.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_dm_agent.py`:

```python
def test_reset_for_new_quest_clears_operational_state(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    # Populate operational keys
    dm.world_state.update({
        "story_arc": {"hook": {"goal": "Fight goblins"}},
        "current_beat": "climax",
        "story_phase": "climax",
        "current_round": 15,
        "remaining_rounds": 5,
        "story_summary": "EVENTS SO FAR:\n- Goblins attacked.",
        "scene_summary": "You stand in the goblin den.",
        "story_complete": True,
        "ending_type": "victory",
        "opening_scene": "You arrive at the gate.",
        "objective": "Defeat the goblin king",
        "location": "Goblin Den",
        "pending_encounter_enemies": ["Goblin"],
        "pending_roll": {"type": "save", "ability": "DEX"},
        "scene_stall_count": 3,
        "recent_party_actions": ["attacked", "fled"],
        "previous_open_threads": "- The cultist escaped.",
        "last_progress_events": ["found_key"],
        "reward_history": ["level:found_key"],
        "story_hook": "A dark conspiracy.",
    })
    # Populate carry-forward keys
    dm.world_state.update({
        "notable_npcs": ["Aria", "Bram", "Captain Voss", "Elder Mira", "Guard Tom", "Spy Lena", "Extra NPC"],
        "nearby_locations": ["Tavern", "Keep"],
        "resolved_events": [f"event_{i}" for i in range(20)],  # 20 events — should be capped to 12
        "campaign_history": ["Quest 1 summary text."],
        "target_rounds": 20,
        "player_name": "Aldric",
    })
    dm.history = [{"role": "user", "content": "I attack"}, {"role": "assistant", "content": "You hit!"}]

    dm.reset_for_new_quest()

    # Operational keys cleared (None or absent — .get() returns None either way)
    for key in [
        "story_arc", "current_beat", "story_phase", "current_round", "remaining_rounds",
        "story_summary", "scene_summary", "story_complete", "ending_type",
        "opening_scene", "objective", "location", "pending_encounter_enemies", "pending_roll",
        "scene_stall_count", "recent_party_actions", "previous_open_threads",
        "last_progress_events", "reward_history", "story_hook",
    ]:
        assert dm.world_state.get(key) is None, f"Expected {key!r} to be cleared"

    # history cleared
    assert dm.history == []

    # Carry-forward keys preserved
    assert dm.world_state["target_rounds"] == 20
    assert dm.world_state["player_name"] == "Aldric"
    assert dm.world_state["campaign_history"] == ["Quest 1 summary text."]
    assert dm.world_state["nearby_locations"] == ["Tavern", "Keep"]

    # resolved_events capped at 12
    assert len(dm.world_state["resolved_events"]) == 12

    # notable_npcs capped at 6
    assert len(dm.world_state["notable_npcs"]) == 6
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_reset_for_new_quest_clears_operational_state -v`
Expected: FAIL with `AttributeError: 'DungeonMaster' object has no attribute 'reset_for_new_quest'`

- [ ] **Step 3: Implement `reset_for_new_quest()` in `dnd/dm/agent.py`**

Add as a new method on `DungeonMaster` (after `_set_fallback_arc`, around line 160):

```python
def reset_for_new_quest(self) -> None:
    """Reset operational world state for a new quest. Carry-forward keys are preserved."""
    keys_to_reset = [
        "story_arc", "current_beat", "story_phase",
        "current_round", "remaining_rounds",
        "story_summary", "scene_summary",
        "story_complete", "ending_type",
        "opening_scene", "objective", "location",
        "pending_encounter_enemies", "pending_roll",
        "scene_stall_count", "recent_party_actions",
        "previous_open_threads", "last_progress_events",
        "reward_history", "story_hook",
    ]
    for key in keys_to_reset:
        self.update_world_state(key, None)

    # Cap notable_npcs at 6 — they carry forward as potential recurring characters
    npcs = self._world_state_list("notable_npcs")[:6]
    self.update_world_state("notable_npcs", npcs)

    # Cap resolved_events at 12 — they carry forward as historical record
    events = self._world_state_list("resolved_events")[-12:]
    self.update_world_state("resolved_events", events)

    # Clear in-memory history — campaign_summary preserves narrative continuity
    self.history = []
```

- [ ] **Step 4: Run test to confirm it passes**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_reset_for_new_quest_clears_operational_state -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: implement reset_for_new_quest on DungeonMaster"
```

---

## Task 3: Implement `generate_campaign_summary()`

**Files:**
- Modify: `dnd/dm/agent.py`
- Test: `tests/test_dm_agent.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_dm_agent.py`:

```python
def test_generate_campaign_summary_appends_to_history(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.world_state.update({
        "story_summary": "EVENTS SO FAR:\n- Party defeated goblins.\nOPEN THREADS:\n- None\nESCALATION LEVEL: Low",
        "resolved_events": ["defeated_goblins"],
        "notable_npcs": ["Aria"],
        "ending_type": "victory",
        "story_arc": {"resolution": {"goal": "Defeat the goblin king"}},
    })

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "The party ventured into the goblin den and triumphed."}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response):
        dm.generate_campaign_summary()

    assert dm.world_state["campaign_history"] == ["The party ventured into the goblin den and triumphed."]


def test_generate_campaign_summary_appends_to_existing_history(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.world_state["campaign_history"] = ["Quest 1 summary."]
    dm.world_state["story_summary"] = "EVENTS SO FAR:\n- Quest 2 events.\nOPEN THREADS:\n- None\nESCALATION LEVEL: Medium"
    dm.world_state["story_arc"] = {"resolution": {"goal": "Complete quest 2"}}

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "Quest 2 summary prose."}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response):
        dm.generate_campaign_summary()

    assert len(dm.world_state["campaign_history"]) == 2
    assert dm.world_state["campaign_history"][0] == "Quest 1 summary."
    assert dm.world_state["campaign_history"][1] == "Quest 2 summary prose."


def test_generate_campaign_summary_falls_back_on_error(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.world_state["story_summary"] = (
        "EVENTS SO FAR:\n- Party defeated goblins.\n"
        "OPEN THREADS:\n- None\nESCALATION LEVEL: Low"
    )

    with patch('dnd.dm.agent.requests.post', side_effect=requests.exceptions.RequestException("boom")):
        dm.generate_campaign_summary()

    history = dm.world_state.get("campaign_history", [])
    assert len(history) == 1
    assert "Party defeated goblins" in history[0]


def test_generate_arc_with_campaign_context_passes_context(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    arc_json = json.dumps({
        "objective": "Find the missing scout",
        "story_hook": "A dark conspiracy",
        "notable_npcs": ["Ranger Kael"],
        "nearby_locations": ["Watchtower"],
        "arc": {
            "hook": {"goal": "Search the forest", "key_npcs": [], "success_condition": "Scout found"},
            "complication": {"goal": "Face the ambush", "key_npcs": [], "success_condition": "Survive"},
            "climax": {"goal": "Confront the conspirators", "key_npcs": [], "success_condition": "Conspirators defeated"},
            "resolution": {"goal": "Return to town", "key_npcs": [], "success_condition": "Town is safe"},
        }
    })
    fake_response = MagicMock()
    fake_response.json.return_value = {"response": arc_json}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response) as mock_post:
        dm.generate_arc("You arrive at the forest edge.", campaign_context="Previous quest summary: goblins were defeated.")

    call_kwargs = mock_post.call_args.kwargs["json"]
    assert "Previous quest summary: goblins were defeated" in call_kwargs["prompt"]
    assert dm.world_state["story_arc"] is not None


def test_generate_arc_without_campaign_context_omits_context(monkeypatch, dm_db):
    """First quest: no campaign_context — prompt must NOT mention previous quest."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    arc_json = json.dumps({
        "objective": "Investigate the village",
        "story_hook": "A mystery",
        "notable_npcs": [],
        "nearby_locations": [],
        "arc": {
            "hook": {"goal": "Investigate", "key_npcs": [], "success_condition": "Clue found"},
            "complication": {"goal": "Face danger", "key_npcs": [], "success_condition": "Danger overcome"},
            "climax": {"goal": "Confront evil", "key_npcs": [], "success_condition": "Evil defeated"},
            "resolution": {"goal": "Restore peace", "key_npcs": [], "success_condition": "Peace restored"},
        }
    })
    fake_response = MagicMock()
    fake_response.json.return_value = {"response": arc_json}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response) as mock_post:
        dm.generate_arc("You stand in the village square.")

    call_kwargs = mock_post.call_args.kwargs["json"]
    assert "Previous quest summary" not in call_kwargs["prompt"]
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_campaign_summary_appends_to_history tests/test_dm_agent.py::test_generate_arc_with_campaign_context_passes_context -v`
Expected: FAIL

- [ ] **Step 3: Implement `generate_campaign_summary()` in `dnd/dm/agent.py`**

Add after `generate_epilogue()` (around line 401):

```python
def generate_campaign_summary(self) -> None:
    """Compress the completed quest into a ~300-word summary appended to campaign_history."""
    from dnd.dm.prompts import CAMPAIGN_SUMMARY_PROMPT

    story_summary = self._get_story_summary()
    resolved_events = ", ".join(self._world_state_list("resolved_events")) or "None recorded"
    notable_npcs = ", ".join(self._world_state_list("notable_npcs")) or "None recorded"
    ending_type = str(self.world_state.get("ending_type", "unknown") or "unknown")
    story_arc = self.world_state.get("story_arc") or {}
    resolution_goal = str(story_arc.get("resolution", {}).get("goal", "") or "")

    prompt = CAMPAIGN_SUMMARY_PROMPT.format(
        story_summary=story_summary,
        resolved_events=resolved_events,
        notable_npcs=notable_npcs,
        ending_type=ending_type,
        resolution_goal=resolution_goal,
    )

    try:
        print(thinking_message("Writing campaign summary"))
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
        print(style(f"[Campaign: {time.time() - _t0:.1f}s]", "gray", dim=True))
        summary = response.json().get("response", "").strip()
        if not summary:
            raise ValueError("Empty campaign summary response")
    except (requests.exceptions.RequestException, ValueError):
        # Fallback: extract the EVENTS SO FAR block from story_summary as plain text
        lines = story_summary.split("\n")
        events = []
        capturing = False
        for line in lines:
            if line.startswith("EVENTS SO FAR"):
                capturing = True
                continue
            if capturing and line.startswith("OPEN THREADS"):
                break
            if capturing and line.strip().startswith("-"):
                events.append(line.lstrip("- ").strip())
        summary = " ".join(events) if events else story_summary[:400]

    history = list(self.world_state.get("campaign_history", []) or [])
    history.append(summary)
    self.update_world_state("campaign_history", history)
```

- [ ] **Step 4: Run all new tests**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py -v`
Expected: All new and existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: implement generate_campaign_summary"
```

---

## Task 4: Implement `generate_downtime_scene()` and extend `generate_opening_scene()`

**Files:**
- Modify: `dnd/dm/agent.py`
- Test: `tests/test_dm_agent.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_dm_agent.py`:

```python
def test_generate_downtime_scene_returns_narration(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.world_state.update({
        "campaign_history": ["The party defeated the goblin king and secured the village."],
        "ending_type": "victory",
        "player_name": "Aldric",
    })

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "Days pass. The village slowly recovers."}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response):
        result = dm.generate_downtime_scene()

    assert "Days pass" in result


def test_generate_downtime_scene_falls_back_on_error(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.world_state["campaign_history"] = ["A quest was completed."]

    with patch('dnd.dm.agent.requests.post', side_effect=requests.exceptions.RequestException("boom")):
        result = dm.generate_downtime_scene()

    assert len(result) > 0


def test_generate_opening_scene_with_campaign_context(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "You find yourself in the haunted forest. What do you do?"}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response) as mock_post:
        opening = dm.generate_opening_scene(player_sheet, {}, campaign_context="Goblins were defeated last time.")

    call_kwargs = mock_post.call_args.kwargs["json"]
    assert "Goblins were defeated last time" in call_kwargs["prompt"]
    assert "What do you do?" in opening


def test_generate_opening_scene_without_campaign_context_unchanged(monkeypatch, dm_db, player_sheet):
    """First quest: campaign_context omitted — prompt must NOT mention previous quest."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "You stand in the market. What do you do?"}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response) as mock_post:
        dm.generate_opening_scene(player_sheet, {})

    call_kwargs = mock_post.call_args.kwargs["json"]
    assert "Previous quest summary" not in call_kwargs["prompt"]
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_downtime_scene_returns_narration tests/test_dm_agent.py::test_generate_opening_scene_with_campaign_context -v`
Expected: FAIL

- [ ] **Step 3: Implement `generate_downtime_scene()` in `dnd/dm/agent.py`**

Add after `generate_campaign_summary()`:

```python
def generate_downtime_scene(self) -> str:
    """Generate a 2-3 paragraph narration bridging the completed quest and the next adventure."""
    from dnd.dm.prompts import DOWNTIME_SCENE_PROMPT

    history = list(self.world_state.get("campaign_history", []) or [])
    campaign_summary = history[-1] if history else "The party completed their previous adventure."
    ending_type = str(self.world_state.get("ending_type", "victory") or "victory")
    player_name = str(self.world_state.get("player_name", "the party") or "the party")

    prompt = DOWNTIME_SCENE_PROMPT.format(
        campaign_summary=campaign_summary,
        ending_type=ending_type,
        player_name=player_name,
    )

    try:
        print(thinking_message("Narrating downtime"))
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
        print(style(f"[Downtime: {time.time() - _t0:.1f}s]", "gray", dim=True))
        narration = response.json().get("response", "").strip()
        if not narration:
            raise ValueError("Empty downtime response")
        return narration
    except (requests.exceptions.RequestException, ValueError):
        return "The party rests and recovers before the next adventure."
```

- [ ] **Step 4: Extend `generate_opening_scene()` to accept `campaign_context`**

Change the method signature (line 42):

```python
def generate_opening_scene(self, player_sheet: CharacterSheet, npcs: dict, campaign_context: str = "") -> str:
```

In the `full_prompt` construction, prepend the campaign context when non-empty. Replace the `full_prompt =` block (lines 53-57):

```python
campaign_block = f"Previous quest summary:\n{campaign_context}\n\n" if campaign_context else ""
full_prompt = (
    f"{campaign_block}"
    f"{player_sheet.get_prompt_summary()}\n\n"
    f"Companions:\n" + "\n".join(npc_summaries) + "\n\n"
    f"{self._pacing_context()}\n\n"
    f"{OPENING_SCENE_PROMPT}"
)
```

- [ ] **Step 5: Run all tests**

Run: `PYTHONPATH=. pytest tests/test_dm_agent.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add dnd/dm/agent.py tests/test_dm_agent.py
git commit -m "feat: implement generate_downtime_scene and extend generate_opening_scene with campaign context"
```

---

## Task 5: Implement `run_level_up_menu()` in `main.py`

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

Note: `tests/test_main.py` already has a module-level import block (`from main import (...)`). Add all new function names to that existing block rather than adding separate import statements.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_main.py` (extend the existing `from main import (...)` block to include `run_level_up_menu`):

```python
def test_run_level_up_menu_calls_level_up_with_rolled_hp(monkeypatch):
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 2}
    player_sheet.class_name = "Cleric"
    player_sheet.spells = []

    with patch("main.roll_dice", return_value=(6, "1d8 → 6")):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_level_up_menu(player_sheet)

    # HP = roll(6) + CON mod(2) = 8, min 1
    player_sheet.level_up.assert_called_once_with(8)


def test_run_level_up_menu_minimum_hp_increase_is_1(monkeypatch):
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d6"
    player_sheet.ability_modifiers = {"CON": -3}
    player_sheet.class_name = "Wizard"
    player_sheet.spells = []

    with patch("main.roll_dice", return_value=(1, "1d6 → 1")):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_level_up_menu(player_sheet)

    # HP = roll(1) + CON(-3) = -2, clamped to 1
    player_sheet.level_up.assert_called_once_with(1)


def test_run_level_up_menu_spell_selection_for_caster(monkeypatch):
    """A caster class with learnable spells shows the selection prompt."""
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 0}
    player_sheet.class_name = "Bard"
    # Bard starts with Cure Wounds; Thunderwave is available but not yet known
    player_sheet.spells = [{"name": "Cure Wounds"}]

    inputs = iter(["1"])  # pick first available spell
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.roll_dice", return_value=(4, "1d8 → 4")):
        run_level_up_menu(player_sheet)

    player_sheet.learn_spell.assert_called_once()


def test_run_level_up_menu_skip_spell_selection(monkeypatch):
    """Choosing 0 skips spell learning."""
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 0}
    player_sheet.class_name = "Bard"
    player_sheet.spells = []

    inputs = iter(["0"])  # skip spell
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.roll_dice", return_value=(4, "1d8 → 4")):
        run_level_up_menu(player_sheet)

    player_sheet.learn_spell.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_run_level_up_menu_calls_level_up_with_rolled_hp -v`
Expected: FAIL with `ImportError` (function not yet in main.py)

- [ ] **Step 3: Implement `run_level_up_menu()` in `main.py`**

Update the data import at line 36 in `main.py`:

```python
from dnd.data import MAX_LEVEL, SPELL_DATA, CLASS_DATA, STORE_INVENTORY
```

Add the function before `main()`:

```python
def run_level_up_menu(player_sheet: "CharacterSheet") -> None:
    """Interactive level-up flow: rolls HP, optionally adds a spell."""
    print(f"\n{section('Level Up')}")
    new_level = player_sheet.level + 1
    print(style(f"You advance to level {new_level}!", "green", bold=True))

    # Roll HP: "1" + hit_die_type (e.g. "d8") → "1d8", then add CON modifier, minimum 1
    con_mod = player_sheet.ability_modifiers.get("CON", 0)
    roll_result, roll_desc = roll_dice("1" + player_sheet.hit_die_type)
    hp_increase = max(1, roll_result + con_mod)
    print(style(f"HP increase: {roll_desc} + CON({con_mod:+d}) = {hp_increase}", "cyan"))
    player_sheet.level_up(hp_increase)

    # Offer spell selection for spellcasting classes
    class_info = CLASS_DATA.get(player_sheet.class_name, {})
    available_spells = class_info.get("spells", [])
    known_names = {s["name"] for s in player_sheet.spells} if player_sheet.spells else set()
    learnable = [s for s in available_spells if s not in known_names]
    if learnable:
        print(style("\nAvailable spells to learn:", "silver"))
        for i, spell_name in enumerate(learnable, 1):
            spell = SPELL_DATA.get(spell_name, {})
            level_label = "Cantrip" if spell.get("level", 0) == 0 else f"Level {spell.get('level', '?')}"
            print(f"  [{i}] {spell_name} ({level_label}) — {spell.get('description', '')[:60]}")
        print("  [0] Skip")
        choice = input(style("Choose a spell to learn (number): ", "cyan")).strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(learnable):
                chosen = learnable[idx]
                player_sheet.learn_spell(chosen)
                print(style(f"You learned {chosen}!", "green"))
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. pytest tests/test_main.py -k "level_up_menu" -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: implement run_level_up_menu with HP roll and spell selection"
```

---

## Task 6: Implement `run_between_quest_menu()` in `main.py`

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

Note: Task 5 must be committed before this task's tests will import cleanly. Add `run_between_quest_menu` to the existing import block in `tests/test_main.py`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_main.py`:

```python
def test_run_between_quest_menu_rest_yes(monkeypatch):
    from unittest.mock import MagicMock
    player_sheet = MagicMock()
    player_sheet.spells = []
    handler = MagicMock()

    inputs = iter(["y", "n", ""])  # rest=yes, shop=no, press enter
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    run_between_quest_menu(player_sheet, handler, level_eligible=False)

    player_sheet.take_long_rest.assert_called_once()
    handler.handle.assert_not_called()


def test_run_between_quest_menu_shop_buy_loop(monkeypatch):
    from unittest.mock import MagicMock
    player_sheet = MagicMock()
    player_sheet.spells = []
    handler = MagicMock()
    handler.handle.return_value = (True, "")

    inputs = iter(["n", "y", "/buy Healing Potion", "done", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    run_between_quest_menu(player_sheet, handler, level_eligible=False)

    player_sheet.take_long_rest.assert_not_called()
    handler.handle.assert_any_call("/shop")
    handler.handle.assert_any_call("/buy Healing Potion")


def test_run_between_quest_menu_triggers_level_up_when_eligible(monkeypatch):
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 0}
    player_sheet.class_name = "Fighter"
    player_sheet.spells = []
    handler = MagicMock()

    inputs = iter(["n", "n", ""])  # no rest, no shop, press enter
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.roll_dice", return_value=(5, "1d8 → 5")):
        run_between_quest_menu(player_sheet, handler, level_eligible=True)

    player_sheet.level_up.assert_called_once_with(5)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_run_between_quest_menu_rest_yes -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `run_between_quest_menu()` in `main.py`**

Add after `run_level_up_menu()`:

```python
def run_between_quest_menu(
    player_sheet: "CharacterSheet",
    handler: "CommandHandler",
    level_eligible: bool = True,
) -> None:
    """Guided between-quest menu: level up → rest → shop."""
    print(f"\n{section('Between Quests')}")
    print(style("Time passes. Before your next adventure...", "silver", italic=True))

    # Level Up
    if level_eligible:
        run_level_up_menu(player_sheet)

    # Rest
    rest_choice = input(style("\nDo you want to take a long rest? [y/N] ", "cyan") + prompt_marker()).strip().lower()
    if rest_choice in {"y", "yes"}:
        player_sheet.take_long_rest()

    # Shop
    shop_choice = input(style("\nDo you want to visit the shop? [y/N] ", "cyan") + prompt_marker()).strip().lower()
    if shop_choice in {"y", "yes"}:
        handler.handle("/shop")
        print(style("Enter /buy <item> to purchase, or press Enter to leave.", "silver", dim=True, italic=True))
        while True:
            buy_input = input(f"\n{prompt_marker()}").strip()
            if not buy_input or buy_input.lower() in {"done", "exit", "leave"}:
                break
            if buy_input.startswith("/buy"):
                handler.handle(buy_input)

    input(style("\nPress Enter to begin your next quest...", "gold", bold=True) + prompt_marker())
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=. pytest tests/test_main.py -k "between_quest" -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: implement run_between_quest_menu with rest and shop flows"
```

---

## Task 7: Implement `run_post_quest_flow()` and wire up completion triggers

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

Add `run_post_quest_flow` to the existing import block in `tests/test_main.py`.

- [ ] **Step 1: Write failing test**

Add to `tests/test_main.py`:

```python
def test_run_post_quest_flow_orchestrates_full_transition(monkeypatch):
    from unittest.mock import MagicMock, patch, call

    dm = MagicMock()
    dm.generate_epilogue.return_value = "The battle ends."
    dm.generate_downtime_scene.return_value = "Weeks pass quietly."
    dm.world_state = {
        "campaign_history": ["The party won."],
        "player_name": "Aldric",
        "target_rounds": 20,
    }

    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 0}
    player_sheet.class_name = "Fighter"
    player_sheet.spells = []

    handler = MagicMock()
    handler.round_number = 25

    npc1 = MagicMock()
    npc2 = MagicMock()
    npcs = {"aria": npc1, "bram": npc2}

    monkeypatch.setattr("main.run_between_quest_menu", lambda *a, **kw: None)

    run_post_quest_flow(dm, npcs, player_sheet, handler, transcript=None)

    dm.generate_epilogue.assert_called_once()
    dm.generate_campaign_summary.assert_called_once()
    dm.generate_downtime_scene.assert_called_once()
    dm.reset_for_new_quest.assert_called_once()

    # NPC state cleared
    assert npc1.history == []
    assert npc1.recent_actions == []
    assert npc2.history == []
    assert npc2.recent_actions == []

    # handler round reset to 1
    assert handler.round_number == 1

    # New arc generated with correct campaign_context
    expected_context = "The party won."
    dm.generate_opening_scene.assert_called_once_with(
        player_sheet, npcs, campaign_context=expected_context
    )
    dm.generate_arc.assert_called_once_with(
        dm.generate_opening_scene.return_value,
        campaign_context=expected_context,
    )
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_run_post_quest_flow_orchestrates_full_transition -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `run_post_quest_flow()` in `main.py`**

Add after `run_between_quest_menu()`:

```python
def run_post_quest_flow(
    dm: "DungeonMaster",
    npcs: dict,
    player_sheet: "CharacterSheet",
    handler: "CommandHandler",
    transcript=None,
) -> None:
    """
    Full post-quest transition: epilogue → campaign summary → downtime →
    between-quest menu → reset → new opening + arc.
    Called when story_complete fires OR round limit is reached.
    """
    # 1. Epilogue
    print(f"\n{speaker('DM', 'gold')} ", end="")
    epilogue = dm.generate_epilogue()
    print(apply_base_style(highlight_quotes(wrap_text(epilogue)), "parchment"))
    if transcript:
        transcript.write_dm_response(epilogue, 0)

    # 2. Campaign summary (persists to DB via update_world_state)
    dm.generate_campaign_summary()

    # 3. Downtime narration
    downtime = dm.generate_downtime_scene()
    print(f"\n{style('— Downtime —', 'silver', italic=True)}")
    print(apply_base_style(highlight_quotes(wrap_text(downtime)), "parchment"))
    if transcript:
        transcript.write_dm_response(downtime, 0)

    # 4. Between-quest menu
    level_eligible = player_sheet.level < MAX_LEVEL
    run_between_quest_menu(player_sheet, handler, level_eligible=level_eligible)

    # 5. Reset world state and clear NPC in-memory state
    dm.reset_for_new_quest()
    for npc in npcs.values():
        npc.history = []
        npc.recent_actions = []
    handler.round_number = 1

    # 6. Generate new opening and arc with campaign context
    campaign_history = list(dm.world_state.get("campaign_history", []) or [])
    campaign_context = campaign_history[-1] if campaign_history else ""
    opening_scene = dm.generate_opening_scene(player_sheet, npcs, campaign_context=campaign_context)
    dm.generate_arc(opening_scene, campaign_context=campaign_context)
    if transcript:
        transcript.write_opening_scene(opening_scene, elapsed=0)
    print(apply_base_style(highlight_quotes(wrap_text(opening_scene)), "parchment"))
    handler.print_turn_status()
    handler.print_suggested_actions()
```

- [ ] **Step 4: Run test**

Run: `PYTHONPATH=. pytest tests/test_main.py::test_run_post_quest_flow_orchestrates_full_transition -v`
Expected: PASS

- [ ] **Step 5: Wire up completion triggers in the main game loop**

**Spectator mode round-limit path** — replace (around line 216):

```python
if handler.round_number > target_rounds:
    print(f"\n{speaker('DM', 'gold')} ", end="")
    epilogue = dm.generate_epilogue()
    print(apply_base_style(highlight_quotes(wrap_text(epilogue)), "parchment"))
    if transcript:
        transcript.write_dm_response(epilogue, 0)
    print(style("\nThe adventure concludes.", "silver", dim=True, italic=True))
    break
```

With:

```python
if handler.round_number > target_rounds:
    run_post_quest_flow(dm, npcs, player_sheet, handler, transcript=transcript)
    continue
```

**`story_is_complete()` path in spectator mode** (around line 241) — replace:

```python
if story_complete:
    print(style("\nThe adventure concludes.", "silver", dim=True, italic=True))
    break
```

With:

```python
if story_complete:
    run_post_quest_flow(dm, npcs, player_sheet, handler, transcript=transcript)
    continue
```

**`story_is_complete()` path in manual mode** (around line 261) — replace:

```python
if story_complete:
    print(style("\nThe adventure concludes.", "silver", dim=True, italic=True))
    break
```

With:

```python
if story_complete:
    run_post_quest_flow(dm, npcs, player_sheet, handler, transcript=transcript)
    continue
```

- [ ] **Step 6: Run full test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: implement run_post_quest_flow and wire up quest chaining triggers"
```

---

## Task 8: Final verification

- [ ] **Step 1: Run complete test suite**

Run: `PYTHONPATH=. pytest -v`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Verify prompts are well-formed**

```bash
PYTHONPATH=. python3 -c "
from dnd.dm.prompts import ARC_GENERATION_PROMPT, CAMPAIGN_SUMMARY_PROMPT, DOWNTIME_SCENE_PROMPT
p = ARC_GENERATION_PROMPT.format(opening_scene='You arrive.', campaign_context='')
assert 'opening_scene' not in p
p2 = ARC_GENERATION_PROMPT.format(opening_scene='You arrive.', campaign_context='Quest 1 summary.')
assert 'Quest 1 summary' in p2
print('Prompts OK')
"
```

Expected: `Prompts OK`

- [ ] **Step 3: Final commit**

```bash
git commit --allow-empty -m "feat: quest chaining system complete

- DungeonMaster: generate_campaign_summary, generate_downtime_scene, reset_for_new_quest
- generate_arc and generate_opening_scene accept optional campaign_context
- CharacterSheet: learn_spell()
- main: run_level_up_menu, run_between_quest_menu, run_post_quest_flow
- Both completion triggers (round limit + story_complete) chain into next quest
- MAX_LEVEL = 20 added to dnd/data.py"
```
