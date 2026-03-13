import pytest
from unittest.mock import MagicMock, patch
import requests
import json

from dnd.database import create_game_session, initialize_database
from dnd.dm.agent import DungeonMaster


@pytest.fixture
def dm_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_dm_agent.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    return create_game_session()


@pytest.fixture
def player_sheet():
    sheet = MagicMock()
    sheet.get_prompt_summary.return_value = "--- Character: Testus (Wizard 1) ---"
    return sheet


def test_generate_opening_scene_persists_and_reuses(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "response": "You stand in the market square of Ashford as bells ring in warning. A breathless courier thrusts a sealed letter into your hands and points toward the northern gate. What do you do?"
    }
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response) as mock_post:
        opening = dm.generate_opening_scene(player_sheet, {})

    assert "What do you do?" in opening
    assert dm.world_state["opening_scene"] == opening
    assert dm.history[-1]["content"] == opening
    mock_post.assert_called_once()

    with patch('dnd.dm.agent.requests.post') as mock_post:
        reused = dm.generate_opening_scene(player_sheet, {})
    assert reused == opening
    mock_post.assert_not_called()


def test_generate_opening_scene_falls_back_on_error(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    with patch('dnd.dm.agent.requests.post', side_effect=requests.exceptions.RequestException("boom")):
        opening = dm.generate_opening_scene(player_sheet, {})

    assert "What do you do?" in opening
    assert dm.world_state["opening_scene"] == opening


def test_format_narration_adds_sections(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    text = (
        "Rain clings to the cobbles outside the guild hall.\n\n"
        "A messenger arrives with news of a raid on the north road.\n\n"
        "You notice a blood-marked map, a shaken apprentice, and a half-open side door."
    )

    formatted = dm._format_narration(text)
    assert "[Scene]" in formatted
    assert "[Problem]" in formatted
    assert "[What Stands Out]" in formatted


def test_format_narration_bolds_character_names(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("player_name", "Mike")
    dm.add_history("assistant", "Garrick and Lyra are ready.")

    text = "Garrick: We should move quickly. Lyra nods to Mike."
    formatted = dm._format_narration(text)

    assert "Garrick" in formatted
    assert "Lyra" in formatted
    assert "Mike" in formatted


def test_format_narration_styles_quotes(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    text = 'Garrick: "We should be cautious," he says. "Goblins are known for their quick movements."'
    formatted = dm._format_narration(text)

    assert '"We should be cautious,"' in formatted
    assert '"Goblins are known for their quick movements."' in formatted


def test_extract_structured_updates_stores_pending_enemies(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    cleaned = dm._extract_structured_updates(
        'The market erupts into chaos as raiders rush the square.\n<encounter enemies="Goblin,Goblin,Wolf,Madeup Beast" />'
    )

    assert "<encounter" not in cleaned
    assert dm.world_state["pending_encounter_enemies"] == ["Goblin", "Goblin", "Wolf"]


def test_extract_structured_updates_stores_pending_roll(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    dm._extract_structured_updates("A trap springs from the floor. Roll a Dexterity saving throw.")

    assert dm.world_state["pending_roll"] == {
        "type": "save",
        "ability": "DEX",
        "label": "Dexterity saving throw",
    }


def test_extract_structured_updates_strips_reward_tags(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    cleaned = dm._extract_structured_updates(
        'You succeed and recover the letter.\n<award_gold amount="20" reason="retrieving the letter" />\n<level_up />'
    )

    assert "<award_gold" not in cleaned
    assert "<level_up" not in cleaned


def test_update_story_progress_tracks_resolved_events_and_location(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    dm._update_story_progress(
        "deliver the letter",
        "The mayor reads the letter with growing concern. This is serious. We need to rally the guards. You reach the edge of the Whispering Woods.",
    )

    assert "letter_delivered" in dm.world_state["resolved_events"]
    assert "mayor_warned" in dm.world_state["resolved_events"]
    assert "defenders_rallied" in dm.world_state["resolved_events"]
    assert dm.world_state["current_location"] == "Whispering Woods edge"
    assert dm.world_state["last_progress_events"]


def test_encounter_guard_tag_ignored_when_guards_are_helping(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    cleaned = dm._extract_structured_updates(
        'The guard nods and says, "Follow me. I can help gather the guards."<encounter enemies="Guard" />'
    )

    assert cleaned
    assert dm.world_state.get("pending_encounter_enemies") in (None, [])


def test_generate_opening_scene_prints_thinking_message(monkeypatch, dm_db, player_sheet, capsys):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    fake_response = MagicMock()
    fake_response.json.return_value = {"response": "A courier races toward you with a sealed message. What do you do?"}
    fake_response.raise_for_status.return_value = None

    with patch('dnd.dm.agent.requests.post', return_value=fake_response):
        dm.generate_opening_scene(player_sheet, {})

    assert "Generating opening scene" in capsys.readouterr().out


def test_generate_response_includes_pacing_context(monkeypatch, dm_db, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("target_rounds", 20)
    dm.update_world_state("current_round", 8)
    dm.update_world_state("remaining_rounds", 12)
    dm.update_world_state("story_phase", "midgame")

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.iter_lines.return_value = [b'{"response":"The trail bends toward the ruins.","done":false}', b'{"done":true}']

    with patch("dnd.dm.agent.requests.post", return_value=fake_response) as mock_post:
        dm.generate_response("Look for tracks.", player_sheet, {})

    prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "Session Pacing:" in prompt
    assert "- Current round: 8" in prompt
    assert "- Target rounds: 20" in prompt
    assert "- Remaining rounds: 12" in prompt
    assert "- Story phase: midgame" in prompt
    assert "Submitted action: Look for tracks." in prompt
    assert "Current turn context:" in prompt
    assert "Arc pressure:" in prompt
    assert "Objective lock:" in prompt


def test_sanitize_dm_response_removes_assistant_continuation(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)

    cleaned = dm._sanitize_dm_response(
        "The guard flinches as the goblin bolts for cover.\n\nWhat do you do next?\nOutcome: The crowd panics.\nAssistant\n\nThe story keeps going.",
        "Aim at the goblin.",
    )

    assert "Assistant" not in cleaned
    assert "Outcome:" not in cleaned
    assert "The story keeps going." not in cleaned
    assert cleaned.endswith("What do you do next?")


def test_sanitize_dm_response_removes_unsubmitted_player_follow_up(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("player_name", "Kraton")

    cleaned = dm._sanitize_dm_response(
        'The goblin springs from the forge and the guard stumbles back.\n\nKraton: "I fire now."\n\nThe bolt thuds into the doorframe.',
        "Raise the crossbow and wait.",
    )

    assert 'Kraton: "I fire now."' not in cleaned
    assert "The goblin springs from the forge" in cleaned
    assert cleaned.endswith("What do you do next?")


def test_arc_pressure_instruction_forces_resolution_when_rounds_low(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("remaining_rounds", 2)

    assert "decisive confrontation" in dm._arc_pressure_instruction()


def test_arc_pressure_instruction_detects_stalled_scene(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("scene_stall_count", 3)
    dm.update_world_state("remaining_rounds", 5)

    assert "Introduce an immediate reveal" in dm._arc_pressure_instruction()


def test_objective_lock_instruction_prefers_current_thread(monkeypatch, dm_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    dm = DungeonMaster(session_id=dm_db)
    dm.update_world_state("objective", "Follow the cloaked man before he leaves town.")
    dm.update_world_state("remaining_rounds", 5)

    assert "do not branch away" in dm._objective_lock_instruction()


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
