# tests/test_npc_agent.py
import pytest
from unittest.mock import MagicMock, patch
from dnd.database import create_game_session, initialize_database, load_npc_memories
from dnd.npc.agent import NPCAgent

@pytest.fixture
def npc_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_npc_agent.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")  # prevent live CLI calls in unit tests
    initialize_database()
    return create_game_session()


def test_npc_agent_raises_without_ollama_host(monkeypatch, npc_db):
    """NPCAgent should raise ValueError when OLLAMA_HOST is not set."""
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    with pytest.raises(ValueError, match="OLLAMA_HOST and OLLAMA_MODEL must be set"):
        NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)


def test_npc_agent_raises_without_ollama_model(monkeypatch, npc_db):
    """NPCAgent should raise ValueError when OLLAMA_MODEL is not set."""
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError, match="OLLAMA_HOST and OLLAMA_MODEL must be set"):
        NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)


def test_npc_agent_raises_without_either(monkeypatch, npc_db):
    """NPCAgent should raise ValueError when both env vars are missing."""
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError):
        NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)


def test_npc_agent_ok_with_both_vars(monkeypatch, npc_db):
    """NPCAgent should initialise without error when both env vars are set."""
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)
    assert agent.name == "Aria"
    assert agent.ollama_host == "http://localhost:11434"
    assert agent.ollama_model == "llama3"
    assert agent._cli_session is None


def test_npc_agent_ok_with_claude_cli(monkeypatch, npc_db):
    """NPCAgent should initialise without Ollama vars when USE_CLAUDE_CLI=true."""
    monkeypatch.setenv("USE_CLAUDE_CLI", "true")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    from dnd.llm import ClaudeCLISession
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)
    assert agent._cli_session is not None
    assert isinstance(agent._cli_session, ClaudeCLISession)


def test_npc_agent_cli_mode_skips_ollama_validation(monkeypatch, npc_db):
    """USE_CLAUDE_CLI=true should bypass the Ollama env-var requirement."""
    monkeypatch.setenv("USE_CLAUDE_CLI", "true")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    # Should not raise
    NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)


def test_npc_agent_remembers_scene(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)
    agent.remember_scene("Player opened the ancient door.")
    assert "Scene memory: Player opened the ancient door." in agent.memory
    assert load_npc_memories(npc_db, "Aria")[-1] == "Scene memory: Player opened the ancient door."


def test_npc_agent_memory_is_capped(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)
    for index in range(20):
        agent.remember(f"memory-{index}")
    assert len(agent.memory) == 12
    assert "memory-0" not in agent.memory
    assert "memory-19" in agent.memory


def test_npc_agent_memory_is_session_scoped(monkeypatch, tmp_path):
    db_path = tmp_path / "test_npc_sessions.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    session_one = create_game_session()
    session_two = create_game_session()
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    agent_one = NPCAgent("Aria", "Ranger", "You are Aria.", session_one)
    agent_one.remember("session-one-memory")

    agent_two = NPCAgent("Aria", "Ranger", "You are Aria.", session_two)
    assert "session-one-memory" not in agent_two.memory


def test_npc_agent_prints_thinking_message(monkeypatch, npc_db, capsys):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)

    fake_response = MagicMock()
    fake_response.iter_lines.return_value = [b'{"response":"We should move quietly.","done":false}', b'{"done":true}']
    fake_response.raise_for_status.return_value = None

    with patch("dnd.npc.agent.requests.post", return_value=fake_response):
        agent.generate_response("What now?", [])

    assert "Aria is thinking" in capsys.readouterr().out


def test_npc_turn_prompt_limits_action_ownership(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)

    captured = {}

    def fake_post(_url, json=None, timeout=None):
        captured["prompt"] = json["prompt"]
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "I move to the doorway and watch for movement."}
        return response

    with patch("dnd.npc.agent.requests.post", side_effect=fake_post):
        agent.generate_turn_action([], "The doorway is dark and quiet.", ["Mike acted: I move to the doorway."])

    assert "Do not narrate the player's actions." in captured["prompt"]
    assert "Do not command the player to cast, attack, or move." in captured["prompt"]
    assert "Here is the current turn context:" in captured["prompt"]
    assert "If the scene momentum is slow or stalled" in captured["prompt"]
    assert "Recent party actions:" in captured["prompt"]
    assert "Mike acted: I move to the doorway." in captured["prompt"]


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


def test_npc_turn_output_strips_own_name_prefix(monkeypatch, npc_db):
    # "Aria: I draw my bow." → own name prefix stripped → returns clean action
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "Aria: I draw my bow on the doorway."}

    with patch("dnd.npc.agent.requests.post", return_value=fake_response):
        action = agent.generate_turn_action([], "The doorway is dark and quiet.")

    assert action == "I draw my bow on the doorway."


def test_npc_turn_output_falls_back_on_outcome_label(monkeypatch, npc_db):
    # "Outcome: ..." → role label → fallback
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "Outcome: Aria moves to the doorway."}

    with patch("dnd.npc.agent.requests.post", return_value=fake_response):
        action = agent.generate_turn_action([], "The doorway is dark and quiet.")

    # Fallback marker is stripped before returning from generate_turn_action
    # The action should be a phase-aware fallback (opening phase since no turn_context)
    assert "keep watch" not in action  # old static fallback should be gone
    assert len(action) > 10  # should be a real sentence


def test_generate_turn_action_uses_requested_actor_type_for_validation(monkeypatch, npc_db):
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {"response": "I hesitate."}

    captured = {}

    def fake_validate_turn_output(*args, **kwargs):
        captured["actor_type"] = kwargs["actor_type"]
        return "Aria commits to the main lead."

    with patch("dnd.npc.agent.requests.post", return_value=fake_response):
        with patch("dnd.npc.agent.validate_turn_output", side_effect=fake_validate_turn_output):
            agent.generate_turn_action([], "The doorway is dark and quiet.", actor_type="player")

    assert captured["actor_type"] == "player"


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
