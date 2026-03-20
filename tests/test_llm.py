"""Tests for dnd/llm.py — ClaudeCLISession and routing logic."""
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
import requests

from dnd.llm import ClaudeCLISession, call_llm, call_llm_stream


# ---------------------------------------------------------------------------
# ClaudeCLISession
# ---------------------------------------------------------------------------

def _make_proc(stdout: str, returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.returncode = returncode
    proc.stderr = ""
    return proc


def _json_output(result: str, session_id: str = "sess-123") -> str:
    return json.dumps({"result": result, "session_id": session_id})


def test_cli_session_returns_result(monkeypatch):
    monkeypatch.delenv("CLAUDE_CLI_MODEL", raising=False)
    proc = _make_proc(_json_output("The goblin attacks!"))
    with patch("subprocess.run", return_value=proc) as mock_run:
        session = ClaudeCLISession()
        result = session.call("What happens?")
    assert result == "The goblin attacks!"
    args = mock_run.call_args[0][0]
    assert "claude" in args
    assert "-p" in args
    assert "--output-format" in args
    assert "json" in args


def test_cli_session_stores_session_id(monkeypatch):
    proc = _make_proc(_json_output("Scene described.", session_id="abc-999"))
    with patch("subprocess.run", return_value=proc):
        session = ClaudeCLISession()
        session.call("Go on.")
    assert session._session_id == "abc-999"


def test_cli_session_passes_resume_on_second_call(monkeypatch):
    proc = _make_proc(_json_output("Continued."))
    with patch("subprocess.run", return_value=proc) as mock_run:
        session = ClaudeCLISession()
        session._session_id = "existing-id"
        session.call("Next turn.")
    args = mock_run.call_args[0][0]
    assert "--resume" in args
    idx = args.index("--resume")
    assert args[idx + 1] == "existing-id"


def test_cli_session_no_resume_on_first_call(monkeypatch):
    proc = _make_proc(_json_output("First response."))
    with patch("subprocess.run", return_value=proc) as mock_run:
        session = ClaudeCLISession()
        session.call("Begin.")
    args = mock_run.call_args[0][0]
    assert "--resume" not in args


def test_cli_session_passes_model(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLI_MODEL", "claude-haiku-4-5")
    proc = _make_proc(_json_output("Haiku response."))
    with patch("subprocess.run", return_value=proc) as mock_run:
        session = ClaudeCLISession()
        session.call("Prompt.")
    args = mock_run.call_args[0][0]
    assert "--model" in args
    idx = args.index("--model")
    assert args[idx + 1] == "claude-haiku-4-5"


def test_cli_session_default_model_when_env_unset(monkeypatch):
    monkeypatch.delenv("CLAUDE_CLI_MODEL", raising=False)
    session = ClaudeCLISession()
    assert session.model == "claude-sonnet-4-6"


def test_cli_session_model_override_in_constructor(monkeypatch):
    monkeypatch.delenv("CLAUDE_CLI_MODEL", raising=False)
    session = ClaudeCLISession(model="claude-opus-4-6")
    assert session.model == "claude-opus-4-6"


def test_cli_session_prepends_system_prompt(monkeypatch):
    proc = _make_proc(_json_output("Response."))
    with patch("subprocess.run", return_value=proc) as mock_run:
        session = ClaudeCLISession()
        session.call("User prompt.", system="You are a DM.")
    args = mock_run.call_args[0][0]
    prompt_arg = args[args.index("-p") + 1]
    assert "You are a DM." in prompt_arg
    assert "User prompt." in prompt_arg


def test_cli_session_raises_on_nonzero_exit(monkeypatch):
    proc = _make_proc("", returncode=1)
    proc.stderr = "something went wrong"
    with patch("subprocess.run", return_value=proc):
        with pytest.raises(requests.exceptions.ConnectionError, match="exited 1"):
            ClaudeCLISession().call("Prompt.")


def test_cli_session_raises_on_file_not_found(monkeypatch):
    with patch("subprocess.run", side_effect=FileNotFoundError("no claude")):
        with pytest.raises(requests.exceptions.ConnectionError, match="not found"):
            ClaudeCLISession().call("Prompt.")


def test_cli_session_raises_on_timeout(monkeypatch):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=30)):
        with pytest.raises(requests.exceptions.ConnectionError, match="timed out"):
            ClaudeCLISession().call("Prompt.")


def test_cli_session_falls_back_to_plain_text_on_json_error(monkeypatch):
    proc = _make_proc("Plain text response without JSON.")
    with patch("subprocess.run", return_value=proc):
        result = ClaudeCLISession().call("Prompt.")
    assert result == "Plain text response without JSON."
    # session_id should remain None since no JSON was parsed
    session = ClaudeCLISession()
    with patch("subprocess.run", return_value=proc):
        session.call("Prompt.")
    assert session._session_id is None


# ---------------------------------------------------------------------------
# call_llm routing
# ---------------------------------------------------------------------------

def test_call_llm_routes_to_cli_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_CLAUDE_CLI", "true")
    mock_session = MagicMock()
    mock_session.call.return_value = "CLI response"
    result = call_llm("Prompt.", cli_session=mock_session)
    mock_session.call.assert_called_once()
    assert result == "CLI response"


def test_call_llm_routes_to_ollama_when_disabled(monkeypatch):
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3")
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"response": "Ollama response"}
    fake_resp.raise_for_status.return_value = None
    with patch("dnd.llm.requests.post", return_value=fake_resp) as mock_post:
        result = call_llm("Prompt.", ollama_host="http://localhost:11434", ollama_model="llama3")
    mock_post.assert_called_once()
    assert result == "Ollama response"


def test_call_llm_ignores_cli_session_when_ollama(monkeypatch):
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")
    mock_session = MagicMock()
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"response": "Ollama."}
    fake_resp.raise_for_status.return_value = None
    with patch("dnd.llm.requests.post", return_value=fake_resp):
        call_llm("Prompt.", ollama_host="http://x", ollama_model="m", cli_session=mock_session)
    mock_session.call.assert_not_called()


def test_call_llm_stream_routes_to_cli(monkeypatch):
    monkeypatch.setenv("USE_CLAUDE_CLI", "true")
    mock_session = MagicMock()
    mock_session.call.return_value = "Streamed CLI response"
    result = call_llm_stream("Prompt.", cli_session=mock_session)
    mock_session.call.assert_called_once()
    assert result == "Streamed CLI response"


def test_call_llm_stream_routes_to_ollama_stream(monkeypatch):
    monkeypatch.setenv("USE_CLAUDE_CLI", "false")
    fake_resp = MagicMock()
    lines = [
        json.dumps({"response": "tok1", "done": False}).encode(),
        json.dumps({"response": "tok2", "done": False}).encode(),
        json.dumps({"done": True}).encode(),
    ]
    fake_resp.iter_lines.return_value = lines
    fake_resp.raise_for_status.return_value = None
    with patch("dnd.llm.requests.post", return_value=fake_resp):
        result = call_llm_stream("Prompt.", ollama_host="http://x", ollama_model="m")
    assert result == "tok1tok2"
