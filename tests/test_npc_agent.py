# tests/test_npc_agent.py
import pytest
from dnd.npc.agent import NPCAgent


def test_npc_agent_raises_without_ollama_host(monkeypatch):
    """NPCAgent should raise ValueError when OLLAMA_HOST is not set."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    with pytest.raises(ValueError, match="OLLAMA_HOST and OLLAMA_MODEL must be set"):
        NPCAgent("Aria", "Ranger", "You are Aria.")


def test_npc_agent_raises_without_ollama_model(monkeypatch):
    """NPCAgent should raise ValueError when OLLAMA_MODEL is not set."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError, match="OLLAMA_HOST and OLLAMA_MODEL must be set"):
        NPCAgent("Aria", "Ranger", "You are Aria.")


def test_npc_agent_raises_without_either(monkeypatch):
    """NPCAgent should raise ValueError when both env vars are missing."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(ValueError):
        NPCAgent("Aria", "Ranger", "You are Aria.")


def test_npc_agent_ok_with_both_vars(monkeypatch):
    """NPCAgent should initialise without error when both env vars are set."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    agent = NPCAgent("Aria", "Ranger", "You are Aria.")
    assert agent.name == "Aria"
    assert agent.ollama_host == "http://localhost:11434"
    assert agent.ollama_model == "llama3"
