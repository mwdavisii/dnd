import os
import requests
import json
import re
from dotenv import load_dotenv
from collections import Counter
from dnd.dm.prompts import OPENING_SCENE_PROMPT, SYSTEM_PROMPT
from dnd.character import CharacterSheet
from dnd.database import load_world_state, save_world_state
from dnd.data import MONSTER_DATA
from dnd.ui import apply_base_style, highlight_quotes, style, thinking_message, wrap_text

load_dotenv()

class DungeonMaster:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.history = []
        self.world_state = load_world_state(session_id)
        self.ollama_host = os.getenv("OLLAMA_HOST")
        self.ollama_model = os.getenv("OLLAMA_MODEL")
        if not self.ollama_host or not self.ollama_model:
            raise ValueError("OLLAMA_HOST and OLLAMA_MODEL must be set in .env file")

    def update_world_state(self, key: str, value):
        """Updates the world state."""
        self.world_state[key] = value
        save_world_state(self.session_id, key, value)

    def add_history(self, role: str, content: str):
        """Appends an entry to the shared narrative history."""
        self.history.append({"role": role, "content": content})

    def generate_opening_scene(self, player_sheet: CharacterSheet, npcs: dict) -> str:
        existing_opening = self.world_state.get("opening_scene")
        if existing_opening:
            if not self.history:
                self.add_history("assistant", existing_opening)
            return existing_opening

        npc_summaries = []
        for npc in npcs.values():
            npc_summaries.append(f"- {npc.name} the {npc.class_name}")

        full_prompt = (
            f"{player_sheet.get_prompt_summary()}\n\n"
            f"Companions:\n" + "\n".join(npc_summaries) + "\n\n"
            f"{self._pacing_context()}\n\n"
            f"{OPENING_SCENE_PROMPT}"
        )

        try:
            print(thinking_message("Generating opening scene"))
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": full_prompt,
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                },
                timeout=(5, 120),
            )
            response.raise_for_status()
            payload = response.json()
            opening_scene = payload.get("response", "").strip()
            if not opening_scene:
                opening_scene = "You arrive in a tense frontier settlement where something has clearly gone wrong. A nervous local hurries toward you with urgent news. What do you do?"

            self.update_world_state("opening_scene", opening_scene)
            self._infer_opening_world_state(opening_scene)
            self.add_history("assistant", opening_scene)
            return opening_scene
        except requests.exceptions.RequestException as e:
            error_message = f"Error connecting to Ollama: {e}"
            print(error_message)
            fallback = "You arrive in a tense frontier settlement where something has clearly gone wrong. A nervous local hurries toward you with urgent news. What do you do?"
            self.update_world_state("opening_scene", fallback)
            self.add_history("assistant", fallback)
            return fallback

    def generate_response(self, prompt: str, player_sheet: CharacterSheet, npcs: dict) -> str:
        self.add_history("user", prompt)
        
        world_state_summary = json.dumps(self.world_state, indent=2)
        
        npc_summaries = []
        for npc in npcs.values():
            npc_summaries.append(f"- {npc.name} the {npc.class_name}")
            
        full_prompt = (
            f"{player_sheet.get_prompt_summary()}\n\n"
            f"Your Companions:\n" + "\n".join(npc_summaries) + "\n\n"
            f"{self._pacing_context()}\n\n"
            f"Current World State:\n{world_state_summary}\n\n"
            "Here is the story so far:\n"
            f"{self._format_history()}"
        )

        try:
            print(thinking_message("DM is thinking"))
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": full_prompt,
                    "system": SYSTEM_PROMPT,
                    "stream": True,
                },
                stream=True,
                timeout=(5, 120),
            )
            response.raise_for_status()

            full_response = []
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    json_line = json.loads(decoded_line)
                    if not json_line.get('done', False):
                        response_part = json_line.get('response', '')
                        full_response.append(response_part)

            final_response = "".join(full_response)
            cleaned_response = self._extract_structured_updates(final_response)
            self._update_story_progress(prompt, cleaned_response)
            self.add_history("assistant", cleaned_response)
            print(apply_base_style(self._format_narration(cleaned_response), "parchment"))
            self._print_pending_encounter_hint()
            return final_response

        except requests.exceptions.RequestException as e:
            error_message = f"Error connecting to Ollama: {e}"
            print(error_message)
            return error_message

    def _format_history(self):
        return "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in self.history])

    def _pacing_context(self) -> str:
        target_rounds = int(self.world_state.get("target_rounds", 0) or 0)
        current_round = int(self.world_state.get("current_round", 1) or 1)
        remaining_rounds = int(self.world_state.get("remaining_rounds", max(target_rounds - current_round, 0)) or 0)
        story_phase = self.world_state.get("story_phase", "opening")
        if target_rounds <= 0:
            return "Session pacing is not configured."
        return (
            "Session Pacing:\n"
            f"- Current round: {current_round}\n"
            f"- Target rounds: {target_rounds}\n"
            f"- Remaining rounds: {remaining_rounds}\n"
            f"- Story phase: {story_phase}"
        )

    def _extract_structured_updates(self, response: str) -> str:
        encounter_match = re.search(r'<encounter enemies="([^"]+)"\s*/>', response)
        if encounter_match:
            enemies = []
            for raw_name in encounter_match.group(1).split(","):
                monster_name = raw_name.strip().title()
                if monster_name in MONSTER_DATA:
                    enemies.append(monster_name)
            if enemies and self._encounter_is_hostile(response, enemies):
                self.update_world_state("pending_encounter_enemies", enemies)
        pending_roll = self._extract_pending_roll(response)
        self.update_world_state("pending_roll", pending_roll)
        cleaned = re.sub(r'\n?\s*<encounter enemies="[^"]+"\s*/>\s*', "\n", response)
        cleaned = re.sub(r'\n?\s*<award_gold amount="[^"]+"(?: reason="[^"]*")?\s*/>\s*', "\n", cleaned)
        cleaned = re.sub(r'\n?\s*<level_up\s*/>\s*', "\n", cleaned)
        return cleaned.strip()

    def _extract_pending_roll(self, response: str) -> dict | None:
        ability_map = {
            "strength": "STR",
            "dexterity": "DEX",
            "constitution": "CON",
            "intelligence": "INT",
            "wisdom": "WIS",
            "charisma": "CHA",
        }
        save_match = re.search(r"Roll a ([A-Za-z]+) saving throw", response, re.IGNORECASE)
        if save_match:
            ability = ability_map.get(save_match.group(1).lower())
            if ability:
                return {"type": "save", "ability": ability, "label": f"{save_match.group(1).title()} saving throw"}

        check_match = re.search(r"(?:Roll|make) a ([A-Za-z]+)(?: \(([^)]+)\))? check", response, re.IGNORECASE)
        if check_match:
            ability = ability_map.get(check_match.group(1).lower())
            if ability:
                label = check_match.group(2).strip() if check_match.group(2) else f"{check_match.group(1).title()} check"
                return {"type": "check", "ability": ability, "label": label}
        return None

    def _print_pending_encounter_hint(self) -> None:
        pending = self.world_state.get("pending_encounter_enemies", [])
        if not pending:
            return
        counts = Counter(pending)
        summary = ", ".join(f"{name} x{count}" if count > 1 else name for name, count in counts.items())
        print(style(f"Enemies spotted: {summary}. Use /encounter to begin initiative.", "red", bold=True))

    def _encounter_is_hostile(self, response: str, enemies: list[str]) -> bool:
        lowered = response.lower()
        hostile_markers = ("attack", "ambush", "charge", "draws a weapon", "hostile", "lunges", "raid", "fight", "snarl")
        calm_guard_markers = ("follow me", "can help", "nods", "listen", "skeptical but", "not unkind", "gather the guards")
        if any(marker in lowered for marker in calm_guard_markers) and set(enemies) == {"Guard"}:
            return False
        return any(marker in lowered for marker in hostile_markers)

    def _update_story_progress(self, user_input: str, response: str) -> None:
        resolved_events = list(self.world_state.get("resolved_events", []))
        new_events = []

        def add_event(event: str):
            if event not in resolved_events:
                resolved_events.append(event)
                new_events.append(event)

        lowered = response.lower()
        if "letter" in lowered and any(phrase in lowered for phrase in ("hands the letter", "reads it", "reads the letter", "deliver the letter", "the letter,")):
            add_event("letter_delivered")
        if ("mayor" in lowered and any(phrase in lowered for phrase in ("urgent news", "warn him", "goblins are raiding", "this is serious"))) or "mayor was warned" in lowered:
            add_event("mayor_warned")
        if any(phrase in lowered for phrase in ("gather the defenders", "rally the guards", "prepare a response", "town's defenders")):
            add_event("defenders_rallied")
        if any(phrase in lowered for phrase in ("reach the edge of the whispering woods", "entrance to the whispering woods", "edge of the whispering woods")):
            self.update_world_state("current_location", "Whispering Woods edge")
        elif any(phrase in lowered for phrase in ("town gates", "push them open", "wooden doors creak")):
            self.update_world_state("current_location", "Town gates")
        elif "mayor's office" in lowered or "mayor's chambers" in lowered:
            self.update_world_state("current_location", "Mayor's office")

        if new_events:
            self.update_world_state("resolved_events", resolved_events[-12:])
        self.update_world_state("last_progress_events", new_events)

    def _infer_opening_world_state(self, opening_scene: str):
        location_match = re.search(r"\b(?:in|at|outside|within) the ([A-Z][A-Za-z' -]+)", opening_scene)
        if location_match and "location" not in self.world_state:
            self.update_world_state("location", location_match.group(1).strip())

        first_sentence = opening_scene.split(".", 1)[0].strip()
        if first_sentence and "objective" not in self.world_state:
            self.update_world_state("objective", first_sentence)

    def _format_narration(self, text: str) -> str:
        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
        names_to_bold = self._names_to_bold()
        if len(paragraphs) <= 1:
            return highlight_quotes(self._bold_names(wrap_text(text), names_to_bold))

        labels = ["[Scene]", "[Problem]", "[What Stands Out]"]
        formatted = []
        for index, paragraph in enumerate(paragraphs):
            label = labels[index] if index < len(labels) else None
            wrapped = highlight_quotes(self._bold_names(wrap_text(paragraph), names_to_bold))
            if label:
                formatted.append(f"{label}\n{wrapped}")
            else:
                formatted.append(wrapped)
        return "\n\n".join(formatted)

    def _names_to_bold(self) -> list[str]:
        names = set()
        player_name = self.world_state.get("player_name")
        if isinstance(player_name, str) and player_name.strip():
            names.add(player_name.strip())
        for entry in self.history:
            content = entry.get("content", "")
            for match in re.findall(r"\b([A-Z][a-z]+)\b", content):
                names.add(match)
        return sorted(names, key=len, reverse=True)

    def _bold_names(self, text: str, names: list[str]) -> str:
        formatted = text
        for name in names:
            formatted = re.sub(rf"\b{re.escape(name)}\b", style(name, bold=True), formatted)
        return formatted
