# tests/test_npc_agent.py
import pytest
from dnd.database import create_game_session, initialize_database, load_npc_memories
from dnd.npc.agent import NPCAgent

@pytest.fixture
def npc_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_npc_agent.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    return create_game_session()


def test_npc_agent_raises_without_ollama_host(monkeypatch, npc_db):
    """NPCAgent should raise ValueError when OLLAMA_HOST is not set."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    with pytest.raises(ValueError, match="OLLAMA_HOST and OLLAMA_MODEL must be set"):
        NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)


def test_npc_agent_raises_without_ollama_model(monkeypatch, npc_db):
    """NPCAgent should raise ValueError when OLLAMA_MODEL is not set."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError, match="OLLAMA_HOST and OLLAMA_MODEL must be set"):
        NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)


def test_npc_agent_raises_without_either(monkeypatch, npc_db):
    """NPCAgent should raise ValueError when both env vars are missing."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError):
        NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)


def test_npc_agent_ok_with_both_vars(monkeypatch, npc_db):
    """NPCAgent should initialise without error when both env vars are set."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.", npc_db)
    assert agent.name == "Aria"
    assert agent.ollama_host == "http://localhost:11434"
    assert agent.ollama_model == "llama3"


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
