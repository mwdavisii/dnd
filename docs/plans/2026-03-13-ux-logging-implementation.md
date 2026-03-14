# UX and Logging Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add save file naming, per-call Ollama timing visible during gameplay, and a structured markdown transcript that replaces the raw TeeStream dump.

**Architecture:** Five independent tasks: (1) trivial save naming UX fix, (2) wrap all Ollama calls with `time.time()` and print elapsed to stdout, (3) build a `TranscriptWriter` class that writes structured markdown to file at key events, (4) change `DungeonMaster.generate_response()` to return `(raw, cleaned)` so the caller can write cleaned text to the transcript, (5) wire `TranscriptWriter` into `main.py` replacing `TeeStream`/`TranscriptSession`.

**Tech Stack:** Python stdlib (`time`, `pathlib`, `datetime`), pytest with `monkeypatch` and `tmp_path`

---

### Task 1: Prompt for save name when no saves exist

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Read `tests/test_main.py` first to understand existing patterns. Then add:

```python
def test_choose_save_file_prompts_for_name_when_no_saves(monkeypatch, tmp_path):
    monkeypatch.setattr("main.list_save_files", lambda: [])
    inputs = iter(["my_adventure"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("main.create_save_path", lambda name=None: str(tmp_path / f"{name}.db"))
    result = choose_save_file()
    assert "my_adventure" in result
```

**Step 2: Run to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_main.py::test_choose_save_file_prompts_for_name_when_no_saves -v
```
Expected: FAIL (current code doesn't prompt)

**Step 3: Update `choose_save_file()` in `main.py`**

Find this block (near the bottom of `choose_save_file()`):
```python
saves = list_save_files()
if not saves:
    return create_save_path()
```

Replace with:
```python
saves = list_save_files()
if not saves:
    save_name = input(f"{style('Name your adventure (leave blank for timestamp)', 'silver')} {prompt_marker()}").strip()
    return create_save_path(save_name or None)
```

**Step 4: Run to verify it passes**

```bash
PYTHONPATH=. pytest tests/test_main.py::test_choose_save_file_prompts_for_name_when_no_saves -v
```

**Step 5: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

**Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: prompt for save name when no saves exist"
```

---

### Task 2: Add Ollama call timing to stdout across all agents

**Files:**
- Modify: `dnd/dm/agent.py`
- Modify: `dnd/npc/agent.py`
- Modify: `dnd/player_agent.py`
- Test: `tests/test_dm_agent.py`, `tests/test_npc_agent.py`, `tests/test_player_agent.py`

**Step 1: Write failing tests**

Add to `tests/test_dm_agent.py`:

```python
def test_generate_opening_scene_prints_timing(monkeypatch, dm_db, player_sheet, capsys):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "You stand in a market square. What do you do?"}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        dm.generate_opening_scene(player_sheet, {})

    out = capsys.readouterr().out
    assert "[Opening:" in out
    assert "s]" in out


def test_generate_response_prints_timing(monkeypatch, dm_db, player_sheet, capsys):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.iter_lines.return_value = [
        b'{"response":"The trail bends.","done":false}',
        b'{"done":true}',
    ]

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        with patch.object(dm, "_evaluate_beat"):
            dm.generate_response("Look around.", player_sheet, {})

    out = capsys.readouterr().out
    assert "[DM:" in out
    assert "s]" in out
```

Add to `tests/test_npc_agent.py`:

```python
def test_generate_turn_action_prints_timing(monkeypatch, npc_db, capsys):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    from dnd.npc.agent import NPCAgent
    npc = NPCAgent(name="Kaelen", class_name="ranger",
                   system_prompt="You are Kaelen.", session_id=npc_db)

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "I cover the exit."}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.npc.agent.requests.post", return_value=fake_response):
        npc.generate_turn_action([], "The enemy approaches.")

    out = capsys.readouterr().out
    assert "[Kaelen:" in out
    assert "s]" in out
```

Add to `tests/test_player_agent.py`:

```python
def test_generate_action_prints_timing(monkeypatch, capsys):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    from unittest.mock import MagicMock, patch
    from dnd.player_agent import AutoPlayerAgent

    sheet = MagicMock()
    sheet.name = "Kraton"
    sheet.get_prompt_summary.return_value = "--- Character: Kraton ---"
    agent = AutoPlayerAgent(sheet)

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "Follow the cloaked man."}
    fake_response.raise_for_status.return_value = None

    with patch("dnd.player_agent.requests.post", return_value=fake_response):
        agent.generate_action("The man is leaving.", [])

    out = capsys.readouterr().out
    assert "[Player:" in out
    assert "s]" in out
```

**Step 2: Run to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_opening_scene_prints_timing tests/test_dm_agent.py::test_generate_response_prints_timing tests/test_npc_agent.py::test_generate_turn_action_prints_timing tests/test_player_agent.py::test_generate_action_prints_timing -v
```

**Step 3: Add `import time` to all three agent files**

Check if `import time` already exists at the top of each file. Add it if missing.

**Step 4: Add timing to `dnd/dm/agent.py`**

In `generate_opening_scene()`, find the `requests.post` call and wrap:

```python
# Before the post call:
_t0 = time.time()

# After response.raise_for_status():
# (existing code to get opening_scene)

# After the opening_scene is set, before the return:
print(style(f"[Opening: {time.time() - _t0:.1f}s]", "gray", dim=True))
```

Place the print just before `self.update_world_state("opening_scene", opening_scene)`.

In `generate_arc()`, wrap similarly:
```python
_t0 = time.time()
# ... existing post call ...
# after JSON parsed and world state updated, before the except:
print(style(f"[Arc: {time.time() - _t0:.1f}s]", "gray", dim=True))
```

Place the print at the end of the `try` block before `except`.

In `generate_response()`, wrap the streaming request:
```python
_t0 = time.time()
# ... existing streaming post and collection ...
# after final_response = "".join(full_response):
print(style(f"[DM: {time.time() - _t0:.1f}s]", "gray", dim=True))
```

Place the print immediately after `final_response = "".join(full_response)`.

In `_evaluate_beat()`, wrap:
```python
_t0 = time.time()
eval_response = requests.post(...)
eval_response.raise_for_status()
raw = eval_response.json().get("response", "").strip().lower()
print(style(f"[Beat: {time.time() - _t0:.1f}s]", "gray", dim=True))
if raw.startswith("yes"):
    ...
```

**Step 5: Add timing to `dnd/npc/agent.py`**

In `generate_response()` (the `ask` command handler), wrap the streaming post:
```python
_t0 = time.time()
# ... existing streaming post ...
final_response = "".join(full_response)
print(style(f"[{self.name}: {time.time() - _t0:.1f}s]", "gray", dim=True))
```

`style` is not currently imported in `npc/agent.py`. Add it:
```python
from dnd.ui import thinking_message, wrap_text, style
```

In `generate_turn_action()`, wrap the non-streaming post:
```python
_t0 = time.time()
response = requests.post(...)
response.raise_for_status()
payload = response.json()
print(style(f"[{self.name}: {time.time() - _t0:.1f}s]", "gray", dim=True))
final_response = validate_turn_output(...)
```

**Step 6: Add timing to `dnd/player_agent.py`**

Wrap the post call:
```python
_t0 = time.time()
response = requests.post(...)
response.raise_for_status()
payload = response.json()
print(style(f"[Player: {time.time() - _t0:.1f}s]", "gray", dim=True))
return validate_turn_output(...)
```

`style` is not currently imported in `player_agent.py`. Add it:
```python
from dnd.ui import thinking_message, style
```

**Step 7: Run timing tests**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_opening_scene_prints_timing tests/test_dm_agent.py::test_generate_response_prints_timing tests/test_npc_agent.py::test_generate_turn_action_prints_timing tests/test_player_agent.py::test_generate_action_prints_timing -v
```

**Step 8: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

**Step 9: Commit**

```bash
git add dnd/dm/agent.py dnd/npc/agent.py dnd/player_agent.py tests/test_dm_agent.py tests/test_npc_agent.py tests/test_player_agent.py
git commit -m "feat: print Ollama call timing after each response"
```

---

### Task 3: Create `TranscriptWriter` class

**Files:**
- Create: `dnd/transcript.py`
- Create: `tests/test_transcript.py`

**Step 1: Write failing tests first**

Create `tests/test_transcript.py`:

```python
import pytest
from pathlib import Path
from dnd.transcript import TranscriptWriter


def test_transcript_writer_creates_header(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.stop()

    content = path.read_text()
    assert "# D&D Session Transcript" in content
    assert "my_save" in content
    assert "llama3" in content


def test_transcript_writer_opening_scene(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_opening_scene("You stand in a market square.", elapsed=3.2)
    writer.stop()

    content = path.read_text()
    assert "## Opening Scene" in content
    assert "3.2s" in content
    assert "You stand in a market square." in content


def test_transcript_writer_round_header(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_round_header(3)
    writer.stop()

    content = path.read_text()
    assert "## Round 3" in content


def test_transcript_writer_player_action(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_player_action("Kraton", "Follow the cloaked man.")
    writer.stop()

    content = path.read_text()
    assert "### Kraton" in content
    assert "Player" in content
    assert "> Follow the cloaked man." in content


def test_transcript_writer_companion_action(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_companion_action("Kaelen", "I cover the exit.")
    writer.stop()

    content = path.read_text()
    assert "### Kaelen" in content
    assert "Companion" in content
    assert "> I cover the exit." in content


def test_transcript_writer_dm_response(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_dm_response("The figure vanishes into an alley.", elapsed=4.1)
    writer.stop()

    content = path.read_text()
    assert "### Dungeon Master" in content
    assert "4.1s" in content
    assert "The figure vanishes into an alley." in content


def test_transcript_writer_stop_is_safe_when_not_started(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.stop()  # Should not raise


def test_transcript_writer_creates_parent_dirs(tmp_path):
    path = tmp_path / "logs" / "nested" / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.stop()
    assert path.exists()
```

**Step 2: Run to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_transcript.py -v
```
Expected: FAIL (module doesn't exist)

**Step 3: Create `dnd/transcript.py`**

```python
import os
from datetime import datetime
from pathlib import Path


class TranscriptWriter:
    """Writes a clean structured markdown transcript of a game session."""

    def __init__(self, path: Path, save_path: str, model: str):
        self.path = path
        self.save_path = save_path
        self.model = model
        self._file = None

    def start(self) -> "TranscriptWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        save_label = Path(self.save_path).stem
        started = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        self._file.write("# D&D Session Transcript\n\n")
        self._file.write("| | |\n|---|---|\n")
        self._file.write(f"| Save | `{save_label}` |\n")
        self._file.write(f"| Started | {started} |\n")
        self._file.write(f"| Model | `{self.model}` |\n\n")
        self._file.write("---\n\n")
        self._file.flush()
        return self

    def stop(self):
        if self._file:
            self._file.close()
            self._file = None

    def write_opening_scene(self, text: str, elapsed: float):
        self._write(f"## Opening Scene *({elapsed:.1f}s)*\n\n{text}\n\n---\n\n")

    def write_round_header(self, round_number: int):
        self._write(f"## Round {round_number}\n\n")

    def write_player_action(self, actor_name: str, action: str):
        self._write(f"### {actor_name} — Player\n\n> {action}\n\n")

    def write_companion_action(self, actor_name: str, action: str):
        self._write(f"### {actor_name} — Companion\n\n> {action}\n\n---\n\n")

    def write_dm_response(self, text: str, elapsed: float):
        self._write(f"### Dungeon Master *({elapsed:.1f}s)*\n\n{text}\n\n---\n\n")

    def _write(self, content: str):
        if self._file:
            self._file.write(content)
            self._file.flush()
```

**Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. pytest tests/test_transcript.py -v
```

**Step 5: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

**Step 6: Commit**

```bash
git add dnd/transcript.py tests/test_transcript.py
git commit -m "feat: add TranscriptWriter for structured markdown transcripts"
```

---

### Task 4: Update `generate_response()` to return `(raw, cleaned)` tuple

**Files:**
- Modify: `dnd/dm/agent.py`
- Modify: `tests/test_dm_agent.py`

The DM's `generate_response()` currently returns `final_response` (the raw LLM output, with XML tags intact). `process_dm_turn()` in `main.py` uses this raw value to detect `<level_up />` and `<award_gold ... />` tags. We also need `cleaned_response` available in `process_dm_turn()` to write to the transcript.

**Step 1: Write a failing test**

Add to `tests/test_dm_agent.py`:

```python
def test_generate_response_returns_raw_and_cleaned_tuple(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.iter_lines.return_value = [
        b'{"response":"The guard nods. <level_up />","done":false}',
        b'{"done":true}',
    ]

    with patch("dnd.dm.agent.requests.post", return_value=fake_response):
        with patch.object(dm, "_evaluate_beat"):
            result = dm.generate_response("Look around.", player_sheet, {})

    assert isinstance(result, tuple)
    raw, cleaned = result
    assert "<level_up />" in raw
    assert "<level_up />" not in cleaned
```

**Step 2: Run to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_returns_raw_and_cleaned_tuple -v
```
Expected: FAIL (result is a string, not a tuple)

**Step 3: Update `generate_response()` in `dnd/dm/agent.py`**

Find the `return final_response` at the end of the success path in `generate_response()`. Change:

```python
return final_response
```

to:

```python
return final_response, cleaned_response
```

**Step 4: Update `process_dm_turn()` in `main.py`** to unpack the tuple

Find this line in `process_dm_turn()`:
```python
response = dm.generate_response(user_input, player_sheet, npcs)
```

Replace with:
```python
raw_response, cleaned_response = dm.generate_response(user_input, player_sheet, npcs)
response = raw_response  # used below for tag detection
```

Then update every reference to `response` that is used for tag detection — they should stay as `response`. The `scene_memory = build_scene_memory(user_input, response)` line should use `raw_response` since it strips tags internally. Actually: look at `build_scene_memory` — it strips XML tags via `re.sub(r"<[^>]+>", " ", response)`, so it works correctly on raw. Leave that as-is.

**Step 5: Run the new test**

```bash
PYTHONPATH=. pytest tests/test_dm_agent.py::test_generate_response_returns_raw_and_cleaned_tuple -v
```

**Step 6: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

**Step 7: Commit**

```bash
git add dnd/dm/agent.py main.py tests/test_dm_agent.py
git commit -m "feat: generate_response returns (raw, cleaned) tuple for transcript support"
```

---

### Task 5: Wire `TranscriptWriter` into `main.py`, remove `TeeStream`/`TranscriptSession`

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Step 1: Write a failing test**

Add to `tests/test_main.py`:

```python
from dnd.transcript import TranscriptWriter


def test_transcript_writer_receives_dm_response(monkeypatch, tmp_path):
    """TranscriptWriter.write_dm_response is called with cleaned text and elapsed."""
    from unittest.mock import MagicMock, patch
    import main as main_module

    transcript = MagicMock(spec=TranscriptWriter)

    fake_dm = MagicMock()
    fake_dm.generate_response.return_value = (
        "Raw response with <level_up />",
        "Cleaned response without tags.",
    )
    fake_dm.world_state = {
        "scene_summary": "",
        "recent_party_actions": [],
        "last_progress_events": [],
        "reward_history": [],
    }

    fake_player = MagicMock()
    fake_player.name = "Kraton"

    fake_handler = MagicMock()

    with patch("main.build_scene_memory", return_value="scene"):
        with patch("main.detect_scene_stall", return_value=False):
            main_module.process_dm_turn(
                "Look around.",
                fake_dm,
                {},
                fake_player,
                {},
                fake_handler,
                transcript=transcript,
            )

    transcript.write_dm_response.assert_called_once()
    args = transcript.write_dm_response.call_args
    assert "Cleaned response without tags." in args[0][0]
    assert isinstance(args[0][1], float)  # elapsed
```

**Step 2: Run to verify it fails**

```bash
PYTHONPATH=. pytest tests/test_main.py::test_transcript_writer_receives_dm_response -v
```

**Step 3: Update `main.py`**

**3a. Add imports** at the top of `main.py`:
```python
import time
from dnd.transcript import TranscriptWriter
```

**3b. Replace `choose_transcript_logging()`:**

Remove the existing function:
```python
def choose_transcript_logging(save_path: str) -> Path | None:
    choice = input(...).strip().lower()
    if choice not in {"y", "yes"}:
        return None
    return create_transcript_path(save_path)
```

Replace with:
```python
def choose_transcript_logging(save_path: str) -> "TranscriptWriter | None":
    choice = input(f"{style('Save a transcript for this session?', 'silver')} {style('[y/N]', 'cyan')} {prompt_marker()}").strip().lower()
    if choice not in {"y", "yes"}:
        return None
    transcript_path = create_transcript_path(save_path)
    model = os.getenv("OLLAMA_MODEL", "unknown")
    return TranscriptWriter(path=transcript_path, save_path=save_path, model=model).start()
```

**3c. Update `main()` to remove `TranscriptSession` and use `TranscriptWriter`:**

Find:
```python
transcript_session = None
```
Change to:
```python
transcript = None
```

Find:
```python
transcript_path = choose_transcript_logging(selected_save)
if transcript_path is not None:
    transcript_session = TranscriptSession(transcript_path, selected_save).start()
    print(style(f"Transcript logging enabled: {transcript_path}", "green", bold=True))
```
Replace with:
```python
transcript = choose_transcript_logging(selected_save)
if transcript is not None:
    print(style(f"Transcript logging enabled.", "green", bold=True))
```

Find the opening scene line and add transcript support:
```python
opening_scene = dm.generate_opening_scene(player_sheet, npcs)
```
Replace with:
```python
_t0 = time.time()
opening_scene = dm.generate_opening_scene(player_sheet, npcs)
_opening_elapsed = time.time() - _t0
dm.generate_arc(opening_scene)
if transcript:
    transcript.write_opening_scene(opening_scene, elapsed=_opening_elapsed)
```
(Remove the separate `dm.generate_arc(opening_scene)` line that follows if it exists.)

Find the `finally` block:
```python
finally:
    if transcript_session is not None:
        transcript_session.stop()
```
Replace with:
```python
finally:
    if transcript is not None:
        transcript.stop()
```

**3d. Update `process_dm_turn()` signature and body:**

Change signature from:
```python
def process_dm_turn(user_input: str, dm, npcs, player_sheet, character_sheets, handler) -> None:
```
to:
```python
def process_dm_turn(user_input: str, dm, npcs, player_sheet, character_sheets, handler, transcript=None) -> None:
```

After the `raw_response, cleaned_response = dm.generate_response(...)` line (from Task 4), add timing and transcript write. Find where `handler.advance_turn()` is called and add before it:

```python
_dm_elapsed = time.time() - _t0  # _t0 set just before dm.generate_response call
if transcript:
    transcript.write_dm_response(cleaned_response, elapsed=_dm_elapsed)
```

You also need to set `_t0 = time.time()` just before the `dm.generate_response()` call:
```python
_t0 = time.time()
raw_response, cleaned_response = dm.generate_response(user_input, player_sheet, npcs)
_dm_elapsed = time.time() - _t0
```

**3e. Update `run_spectator_turn()` to write player and companion actions to transcript:**

Change signature:
```python
def run_spectator_turn(handler, dm, player_sheet, player_agent) -> str | None:
```
to:
```python
def run_spectator_turn(handler, dm, player_sheet, player_agent, transcript=None) -> str | None:
```

After `action = player_agent.generate_action(...)` and before `return action`, add:
```python
if transcript and action:
    transcript.write_player_action(player_sheet.name, action)
```

After `handler.handle("/npcturn")`, the NPC has already printed its action. We need to capture the actor name for the transcript. Add before `return None`:
```python
if transcript:
    transcript.write_companion_action(actor["name"], "")
```
Wait — we don't have the NPC's action text here since it's handled deep in CommandHandler. For now, just write the round header and player/DM, and skip companion text in transcript (it shows in stdout). Remove the companion write for now.

**3f. Update the main game loop to pass `transcript` to these functions:**

Find all calls to `process_dm_turn(...)` in the main loop and add `transcript=transcript`:
```python
process_dm_turn(action, dm, npcs, player_sheet, character_sheets, handler, transcript=transcript)
```
and:
```python
process_dm_turn(user_input, dm, npcs, player_sheet, character_sheets, handler, transcript=transcript)
```

Find the call to `run_spectator_turn(...)` and update:
```python
action = run_spectator_turn(handler, dm, player_sheet, player_agent, transcript=transcript)
```

**3g. Add round header to transcript in the spectator loop:**

Just before `run_spectator_turn(...)` in the spectator loop, add:
```python
if transcript and actor["type"] == "player":
    transcript.write_round_header(handler.round_number)
```

**3h. Delete `TeeStream` and `TranscriptSession` classes** from `main.py` — find and remove the two class definitions entirely.

**Step 4: Run the new test**

```bash
PYTHONPATH=. pytest tests/test_main.py::test_transcript_writer_receives_dm_response -v
```

**Step 5: Run full suite**

```bash
PYTHONPATH=. pytest -v
```

**Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: wire TranscriptWriter into main.py, remove TeeStream"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `main.py` | Prompt for save name when no saves; replace `TeeStream`/`TranscriptSession` with `TranscriptWriter`; pass transcript to `process_dm_turn()` and `run_spectator_turn()`; time opening scene |
| `dnd/dm/agent.py` | Add `time.time()` timing + print for opening, arc, response, beat eval; change `generate_response()` return to `(raw, cleaned)` |
| `dnd/npc/agent.py` | Add timing + print for `generate_response()` and `generate_turn_action()`; add `style` import |
| `dnd/player_agent.py` | Add timing + print for `generate_action()`; add `style` import |
| `dnd/transcript.py` | New file: `TranscriptWriter` class |
| `tests/test_transcript.py` | New file: 8 tests for `TranscriptWriter` |
| `tests/test_dm_agent.py` | 2 new tests: timing output, return type |
| `tests/test_npc_agent.py` | 1 new test: timing output |
| `tests/test_player_agent.py` | 1 new test: timing output |
| `tests/test_main.py` | 2 new tests: save naming, transcript wiring |
