import pytest
from unittest.mock import MagicMock, patch
import requests

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
