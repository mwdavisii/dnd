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
    assert "Turn context:" in prompt
    assert "Recent party actions:" in prompt
    assert "Kaelen acted: Moves toward the ridge." in prompt
    assert "Respond in plain English only." in prompt
    assert "Use ASCII characters only." in prompt
    assert "When scene momentum is slow or stalled" in prompt


def test_auto_player_agent_falls_back_on_non_latin_response(monkeypatch, player_sheet):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = AutoPlayerAgent(player_sheet)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "Kraton细心地检查了一下他的口袋。"}

    with patch("dnd.player_agent.requests.post", return_value=fake_response):
        action = agent.generate_action("The square is tense.", [])

    assert action == "Mike studies the scene, moves toward the clearest lead, and stays ready to react."


def test_auto_player_agent_strips_role_label_and_actor_prefix(monkeypatch, player_sheet):
    # "DM: Mike: ..." → strips DM: role label, then strips "Mike:" actor prefix → returns clean action
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = AutoPlayerAgent(player_sheet)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "DM: Mike: I cast a spell at the guard."}

    with patch("dnd.player_agent.requests.post", return_value=fake_response):
        action = agent.generate_action("The square is tense.", [])

    assert action == "I cast a spell at the guard."


def test_auto_player_agent_falls_back_on_result_label_output(monkeypatch, player_sheet):
    # "Result: ..." → role label caught by _strip_other_speaker_labels → empty → fallback
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = AutoPlayerAgent(player_sheet)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "Result: The adventurers press forward."}

    with patch("dnd.player_agent.requests.post", return_value=fake_response):
        action = agent.generate_action("The square is tense.", [])

    assert action == "Mike studies the scene, moves toward the clearest lead, and stays ready to react."


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


def test_generate_action_includes_beat_goal(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    from unittest.mock import MagicMock, patch
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
