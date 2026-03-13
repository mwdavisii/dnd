import os
import requests
from dotenv import load_dotenv

from dnd.ui import thinking_message
from dnd.spectator import default_fallback_action, format_turn_context, validate_turn_output

load_dotenv()


class AutoPlayerAgent:
    def __init__(self, player_sheet):
        self.player_sheet = player_sheet
        self.ollama_host = os.getenv("OLLAMA_HOST")
        self.ollama_model = os.getenv("OLLAMA_MODEL")
        if not self.ollama_host or not self.ollama_model:
            raise ValueError("OLLAMA_HOST and OLLAMA_MODEL must be set in .env file")

    def generate_action(
        self,
        scene_summary: str,
        recent_party_actions: list[str],
        turn_context: dict | None = None,
    ) -> str:
        context_block = format_turn_context(turn_context) if turn_context else scene_summary
        beat_goal = (turn_context or {}).get("current_beat_goal", "")
        beat_goal_line = f"Current goal: {beat_goal}\n" if beat_goal else ""

        prompt = (
            "You are controlling the player character in spectator mode.\n"
            "Choose one short, concrete action that moves the scene forward.\n"
            "Respond in plain English only.\n"
            "Use ASCII characters only.\n"
            "Stay in character. Do not explain your reasoning. Do not write multiple options.\n"
            "Do not narrate outcomes, other speakers, or future turns.\n"
            "Do not include labels such as DM:, Assistant:, Outcome:, or your own name.\n\n"
            f"{beat_goal_line}"
            "Prefer actions that create progress: question, inspect, advance, rescue, confront, cast, strike, or seize evidence.\n"
            "Avoid repeating the same cautious movement unless immediate danger clearly forces it.\n"
            "When scene momentum is slow or stalled, do something that reveals information or forces a change.\n"
            "When only a few rounds remain, choose a decisive action instead of another setup action.\n\n"
            f"{self.player_sheet.get_prompt_summary()}\n"
            f"Turn context:\n{context_block}\n\n"
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
        return validate_turn_output(
            payload.get("response", "").strip(),
            actor_name=self.player_sheet.name,
            actor_type="player",
            recent_party_actions=recent_party_actions,
            turn_context=turn_context,
            fallback=default_fallback_action(self.player_sheet.name, "player"),
        )
