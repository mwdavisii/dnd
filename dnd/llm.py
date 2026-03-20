"""
Shared LLM backend dispatcher.

Set USE_CLAUDE_CLI=true in .env to route all LLM calls through the local `claude`
CLI instead of Ollama.  Both backends raise requests.exceptions.RequestException
on failure so that existing callers don't need to change their except clauses.
"""
import json
import os
import subprocess

import requests


class ClaudeCLISession:
    """Wraps `claude -p` with session persistence and configurable model.

    After the first call the CLI returns a session_id in its JSON output.
    Subsequent calls pass --resume <session_id> so the model has real
    conversation context without re-sending the full history every turn.

    Model is read from CLAUDE_CLI_MODEL env var (default: claude-sonnet-4-6).
    Set CLAUDE_CLI_MODEL=claude-haiku-4-5 (or any valid model ID) to override.
    """

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("CLAUDE_CLI_MODEL", "claude-sonnet-4-6")
        self._session_id: str | None = None

    def call(self, prompt: str, system: str | None = None, timeout: int = 120) -> str:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        cmd = [
            "claude", "-p", full_prompt,
            "--output-format", "json",
            "--model", self.model,
        ]
        if self._session_id:
            cmd += ["--resume", self._session_id]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise requests.exceptions.ConnectionError(f"claude CLI timed out: {e}") from e
        except FileNotFoundError as e:
            raise requests.exceptions.ConnectionError(
                "claude CLI not found — is it on your PATH?"
            ) from e

        if result.returncode != 0:
            raise requests.exceptions.ConnectionError(
                f"claude CLI exited {result.returncode}: {result.stderr.strip()}"
            )

        try:
            data = json.loads(result.stdout)
            if data.get("session_id"):
                self._session_id = data["session_id"]
            return (data.get("result") or "").strip()
        except json.JSONDecodeError:
            # Fallback: treat raw stdout as plain text (e.g. older CLI versions)
            return result.stdout.strip()


def call_llm(
    prompt: str,
    system: str | None = None,
    ollama_host: str | None = None,
    ollama_model: str | None = None,
    timeout: tuple[int, int] = (5, 120),
    cli_session: ClaudeCLISession | None = None,
) -> str:
    """Call the configured LLM and return the full response string.

    Routing:
      USE_CLAUDE_CLI=true  →  local `claude -p` subprocess (via cli_session)
      (default)            →  Ollama /api/generate (non-streaming)
    """
    use_claude_cli = os.getenv("USE_CLAUDE_CLI", "").lower() == "true"
    if use_claude_cli:
        session = cli_session or ClaudeCLISession()
        return session.call(prompt, system, timeout=timeout[1])
    return _call_ollama(prompt, system, ollama_host, ollama_model, timeout)


def call_llm_stream(
    prompt: str,
    system: str | None = None,
    ollama_host: str | None = None,
    ollama_model: str | None = None,
    timeout: tuple[int, int] = (5, 120),
    cli_session: ClaudeCLISession | None = None,
) -> str:
    """Like call_llm but uses Ollama streaming when not using Claude CLI.

    Tokens are collected and returned as a single string — identical result,
    just fetched with stream=True on the Ollama side.
    """
    use_claude_cli = os.getenv("USE_CLAUDE_CLI", "").lower() == "true"
    if use_claude_cli:
        session = cli_session or ClaudeCLISession()
        return session.call(prompt, system, timeout=timeout[1])
    return _call_ollama_stream(prompt, system, ollama_host, ollama_model, timeout)


# ---------------------------------------------------------------------------
# Internal backends
# ---------------------------------------------------------------------------

def _call_ollama(
    prompt: str,
    system: str | None,
    ollama_host: str,
    ollama_model: str,
    timeout: tuple[int, int],
) -> str:
    payload: dict = {"model": ollama_model, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system
    response = requests.post(
        f"{ollama_host}/api/generate",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def _call_ollama_stream(
    prompt: str,
    system: str | None,
    ollama_host: str,
    ollama_model: str,
    timeout: tuple[int, int],
) -> str:
    payload: dict = {"model": ollama_model, "prompt": prompt, "stream": True}
    if system:
        payload["system"] = system
    response = requests.post(
        f"{ollama_host}/api/generate",
        json=payload,
        stream=True,
        timeout=timeout,
    )
    response.raise_for_status()
    parts: list[str] = []
    for line in response.iter_lines():
        if line:
            json_line = json.loads(line.decode("utf-8"))
            if not json_line.get("done", False):
                parts.append(json_line.get("response", ""))
    return "".join(parts)
