from unittest.mock import MagicMock, patch

import pytest

from dnd.player_agent import AutoPlayerAgent


@pytest.fixture
def player_sheet():
    sheet = MagicMock()
    sheet.name = "Mike"
    sheet.get_prompt_summary.return_value = "--- Character: Mike (Warlock 1) ---"
    return sheet


def test_auto_player_agent_generates_action(monkeypatch, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = AutoPlayerAgent(player_sheet)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "Head toward the torchlight with Kaelen."}

    with patch("dnd.player_agent.requests.post", return_value=fake_response) as mock_post:
        action = agent.generate_action("A torch flickers in the trees.", ["Kaelen acted: Moves toward the ridge."])

    assert action == "Head toward the torchlight with Kaelen."
    prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "Scene summary:" in prompt
    assert "Recent party actions:" in prompt
    assert "Kaelen acted: Moves toward the ridge." in prompt
