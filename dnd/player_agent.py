import os
import re
import requests
from dotenv import load_dotenv

from dnd.ui import thinking_message

load_dotenv()


class AutoPlayerAgent:
    def __init__(self, player_sheet):
        self.player_sheet = player_sheet
        self.ollama_host = os.getenv("OLLAMA_HOST")
        self.ollama_model = os.getenv("OLLAMA_MODEL")
        if not self.ollama_host or not self.ollama_model:
            raise ValueError("OLLAMA_HOST and OLLAMA_MODEL must be set in .env file")

    def generate_action(self, scene_summary: str, recent_party_actions: list[str]) -> str:
        prompt = (
            "You are controlling the player character in spectator mode.\n"
            "Choose one short, concrete action that moves the scene forward.\n"
            "Respond in plain English only.\n"
            "Use ASCII characters only.\n"
            "Stay in character. Do not explain your reasoning. Do not write multiple options.\n\n"
            f"{self.player_sheet.get_prompt_summary()}\n"
            f"Scene summary:\n{scene_summary}\n\n"
            "Recent party actions:\n"
            + ("\n".join(f"- {action}" for action in recent_party_actions[-3:]) if recent_party_actions else "- None recorded.")
        )

        print(thinking_message(f"{self.player_sheet.name} is thinking"))
        response = requests.post(
            f"{self.ollama_host}/api/generate",
            json={
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=(5, 120),
        )
        response.raise_for_status()
        payload = response.json()
        return self._normalize_action(payload.get("response", "").strip())

    def _normalize_action(self, action: str) -> str:
        if not action:
            return "Look around carefully."

        cleaned = " ".join(action.split())
        if self._contains_non_latin_script(cleaned):
            return "Check your gear and scan the area carefully."
        return cleaned

    def _contains_non_latin_script(self, text: str) -> bool:
        return bool(re.search(r"[\u0400-\u052F\u0590-\u05FF\u0600-\u06FF\u0900-\u0D7F\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF]", text))
