import os
import time
import requests
import json
import re
from dotenv import load_dotenv
from collections import Counter
from dnd.dm.prompts import ARC_GENERATION_PROMPT, BEAT_EVALUATION_PROMPT, OPENING_SCENE_PROMPT, STORY_SUMMARY_PROMPT, SYSTEM_PROMPT
from dnd.character import CharacterSheet
from dnd.database import load_world_state, save_world_state
from dnd.data import _BEAT_PHASE, MONSTER_DATA
from dnd.spectator import format_turn_context, momentum_label, phase_goal
from dnd.ui import apply_base_style, highlight_quotes, style, thinking_message, wrap_text

load_dotenv()

_BEAT_DEADLINES = {"hook": 0.20, "complication": 0.50, "climax": 0.75}
_ENDING_TYPES = {"victory", "defeat", "escape", "sacrifice"}

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

    def story_is_complete(self) -> bool:
        return bool(self.world_state.get("story_complete", False))

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
            _t0 = time.time()
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
            print(style(f"[Opening: {time.time() - _t0:.1f}s]", "gray", dim=True))
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

    def generate_arc(self, opening_scene: str) -> None:
        """Generate a 4-beat story arc from the opening scene. Skips if arc already exists (saved game)."""
        if self.world_state.get("story_arc"):
            return

        prompt = ARC_GENERATION_PROMPT.format(opening_scene=opening_scene)
        try:
            print(thinking_message("Generating story arc"))
            _t0 = time.time()
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
            print(style(f"[Arc: {time.time() - _t0:.1f}s]", "gray", dim=True))
            raw = response.json().get("response", "").strip()
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            arc_data = json.loads(json_match.group() if json_match else raw)

            if not arc_data.get("arc"):
                self._set_fallback_arc()
                return

            self.update_world_state("story_arc", arc_data.get("arc", {}))
            self.update_world_state("current_beat", "hook")
            if arc_data.get("objective"):
                self.update_world_state("objective", arc_data["objective"])
            if arc_data.get("notable_npcs"):
                self.update_world_state("notable_npcs", arc_data["notable_npcs"])
            if arc_data.get("nearby_locations"):
                self.update_world_state("nearby_locations", arc_data["nearby_locations"])
            if arc_data.get("story_hook"):
                self.update_world_state("story_hook", arc_data["story_hook"])
        except (requests.exceptions.RequestException, json.JSONDecodeError, AttributeError):
            self._set_fallback_arc()

    def _set_fallback_arc(self) -> None:
        """Set a generic 4-beat arc when arc generation fails."""
        objective = str(self.world_state.get("objective", "Investigate the situation") or "Investigate the situation")
        fallback = {
            "hook": {
                "goal": f"Pursue the opening lead: {objective}",
                "key_npcs": [],
                "success_condition": "The party identifies the main threat or mystery.",
            },
            "complication": {
                "goal": "Overcome the first obstacle blocking your path.",
                "key_npcs": [],
                "success_condition": "The party faces a setback or discovers a deeper problem.",
            },
            "climax": {
                "goal": "Confront the main threat directly.",
                "key_npcs": [],
                "success_condition": "The main conflict reaches a decisive moment.",
            },
            "resolution": {
                "goal": "Resolve the conflict and show its consequences.",
                "key_npcs": [],
                "success_condition": "The story reaches a clear conclusion.",
            },
        }
        self.update_world_state("story_arc", fallback)
        self.update_world_state("current_beat", "hook")

    def _beat_past_deadline(self, current_beat: str) -> bool:
        """Return True if the current round has passed the beat's hard deadline."""
        current_round = int(self.world_state.get("current_round", 1) or 1)
        target_rounds = int(self.world_state.get("target_rounds", 0) or 0)
        if target_rounds <= 0:
            return False
        deadline_ratio = _BEAT_DEADLINES.get(current_beat)
        if deadline_ratio is None:
            return False
        return (current_round / target_rounds) >= deadline_ratio

    def _evaluate_beat(self, response: str) -> None:
        """Check if the current story beat's success condition is met via LLM and advance if so.

        Deadline-based advancement is handled earlier by _advance_beat_if_past_deadline().
        This method only performs the LLM-based evaluation for early advancement.
        """
        story_arc = self.world_state.get("story_arc")
        if not story_arc:
            return

        beat_order = ["hook", "complication", "climax", "resolution"]
        current_beat = str(self.world_state.get("current_beat", "hook") or "hook")
        if current_beat not in beat_order:
            return
        current_idx = beat_order.index(current_beat)
        if current_idx >= len(beat_order) - 1:
            return  # Already at resolution

        success_condition = str(story_arc.get(current_beat, {}).get("success_condition", "") or "")
        if not success_condition:
            return

        prompt = BEAT_EVALUATION_PROMPT.format(
            success_condition=success_condition,
            dm_response=response[:900],
        )
        try:
            _t0 = time.time()
            eval_response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=(5, 30),
            )
            eval_response.raise_for_status()
            print(style(f"[Beat: {time.time() - _t0:.1f}s]", "gray", dim=True))
            raw = eval_response.json().get("response", "").strip().lower()
            if raw.startswith("yes"):
                next_beat = beat_order[current_idx + 1]
                self.update_world_state("current_beat", next_beat)
                self.update_world_state("story_phase", _BEAT_PHASE[next_beat])
        except requests.exceptions.RequestException:
            pass  # Silently skip on network error

    def _update_story_summary(self, player_action: str, dm_response: str) -> None:
        """Update the rolling story summary with the latest turn's events."""
        previous_summary = str(self.world_state.get("story_summary", "") or "").strip()
        if not previous_summary:
            previous_summary = "No prior summary. This is the first update."

        story_arc = self.world_state.get("story_arc") or {}
        current_beat = str(self.world_state.get("current_beat", "hook") or "hook")
        beat_goal = str(story_arc.get(current_beat, {}).get("goal", "") or "")

        prompt = STORY_SUMMARY_PROMPT.format(
            previous_summary=previous_summary,
            current_beat=current_beat,
            beat_goal=beat_goal,
            player_action=player_action[:200],
            dm_response=dm_response[:800],
        )

        try:
            _t0 = time.time()
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=(5, 60),
            )
            response.raise_for_status()
            print(style(f"[Summary: {time.time() - _t0:.1f}s]", "gray", dim=True))
            raw = response.json().get("response", "").strip()
            if raw and "EVENTS SO FAR" in raw and "OPEN THREADS" in raw:
                self.update_world_state("story_summary", raw)
        except requests.exceptions.RequestException:
            pass  # Keep previous summary on error

    def _advance_beat_if_past_deadline(self) -> None:
        """Force-advance the current beat if the round has passed its hard deadline.

        Called BEFORE building the DM prompt so the DM sees the correct phase.
        """
        story_arc = self.world_state.get("story_arc")
        if not story_arc:
            return
        beat_order = ["hook", "complication", "climax", "resolution"]
        current_beat = str(self.world_state.get("current_beat", "hook") or "hook")
        if current_beat not in beat_order:
            return
        current_idx = beat_order.index(current_beat)
        if current_idx >= len(beat_order) - 1:
            return
        if self._beat_past_deadline(current_beat):
            next_beat = beat_order[current_idx + 1]
            self.update_world_state("current_beat", next_beat)
            self.update_world_state("story_phase", _BEAT_PHASE[next_beat])

    def generate_response(self, prompt: str, player_sheet: CharacterSheet, npcs: dict) -> tuple[str, str]:
        self.add_history("user", prompt)
        self._advance_beat_if_past_deadline()

        npc_summaries = []
        for npc in npcs.values():
            npc_summaries.append(f"- {npc.name} the {npc.class_name}")

        in_resolution = self.world_state.get("story_phase") == "resolution"
        ending_instruction = (
            "Do not ask what the player does next. Narrate a satisfying conclusion."
            if in_resolution
            else "End with one direct question asking what the player does next."
        )

        full_prompt = (
            f"{player_sheet.get_prompt_summary()}\n\n"
            f"Your Companions:\n" + "\n".join(npc_summaries) + "\n\n"
            f"{self._pacing_context()}\n\n"
            f"{self._dm_scene_context(prompt)}\n\n"
            "Story so far:\n"
            f"{self._get_story_summary()}\n\n"
            "Last turn:\n"
            f"{self._recent_history_summary(max_entries=3)}\n\n"
            "Resolve only the submitted action and the world's immediate response.\n"
            "Do not add extra assistant turns, recap loops, or speculative follow-up actions by the player.\n"
            "Do not include labels such as Assistant:, User:, Outcome:, or repeated speaker prefixes.\n"
            "Do not contradict recent progress or resolved events already established in world state.\n"
            f"Arc directive: {self._arc_pressure_instruction()}\n"
            f"{ending_instruction}"
        )

        try:
            print(thinking_message("DM is thinking"))
            _t0 = time.time()
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
            print(style(f"[DM: {time.time() - _t0:.1f}s]", "gray", dim=True))
            # Order matters: _sanitize_dm_response checks for ending tags (e.g. <ending type="victory" />)
            # to decide whether to append "What do you do next?". _extract_structured_updates then
            # strips those tags from the cleaned text. Reversing the order would break ending detection.
            cleaned_response = self._sanitize_dm_response(final_response, prompt)
            cleaned_response = self._extract_structured_updates(cleaned_response)
            self._evaluate_beat(cleaned_response)
            self._update_story_summary(prompt, cleaned_response)
            self.add_history("assistant", cleaned_response)
            print(apply_base_style(self._format_narration(cleaned_response), "parchment"))
            self._print_pending_encounter_hint()
            return final_response, cleaned_response

        except requests.exceptions.RequestException as e:
            error_message = f"Error connecting to Ollama: {e}"
            print(error_message)
            return error_message, error_message

    def generate_epilogue(self) -> str:
        """Generate a dedicated conclusion scene that wraps up the story."""
        story_summary = self._get_story_summary()
        recent_story = self._recent_history_summary(max_entries=3)
        objective = str(self.world_state.get("objective", "") or "")
        story_arc = self.world_state.get("story_arc") or {}
        resolution_goal = str(story_arc.get("resolution", {}).get("goal", "") or "")

        prompt = (
            "You are narrating the final scene of a short D&D adventure.\n\n"
            f"The party's objective was: {objective}\n"
            f"The resolution goal is: {resolution_goal}\n\n"
            "Full story so far:\n"
            f"{story_summary}\n\n"
            "Most recent events:\n"
            f"{recent_story}\n\n"
            "Write a 2-3 paragraph CONCLUSION that:\n"
            "1. Resolves the central conflict based on what ACTUALLY happened in the story above\n"
            "2. References specific characters, places, and events from the story — do NOT invent new ones\n"
            "3. Shows what happens to the main characters afterward\n"
            "4. Ends with a final closing sentence — do NOT ask what the player does next\n"
            "5. Do NOT introduce new threats, mysteries, cliffhangers, or dice rolls\n"
            "6. Do NOT contradict events that already happened\n"
            "7. Keep it under 200 words\n\n"
            "Write only the conclusion narration. No labels, no meta-commentary."
        )

        try:
            print(thinking_message("Writing the epilogue"))
            _t0 = time.time()
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
            print(style(f"[Epilogue: {time.time() - _t0:.1f}s]", "gray", dim=True))
            raw = response.json().get("response", "").strip()
            if not raw:
                raw = "The adventure draws to a close. The party stands together, battered but unbroken, as the dust settles on what has been a harrowing journey."
            # Strip any lingering "What do you do?" from the epilogue
            raw = re.sub(r"(?m)\s*What do you do.*$", "", raw, flags=re.IGNORECASE).strip()
            return raw
        except requests.exceptions.RequestException as e:
            print(f"Error generating epilogue: {e}")
            return "The adventure draws to a close. The party stands together, battered but unbroken, as the dust settles on what has been a harrowing journey."

    def _format_history(self):
        return "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in self.history])

    def _get_story_summary(self) -> str:
        """Return the rolling story summary, or a placeholder if none exists yet."""
        summary = str(self.world_state.get("story_summary", "") or "").strip()
        if not summary:
            return "No story summary yet — this is the beginning of the adventure."
        return summary

    def _recent_history_summary(self, max_entries: int = 6) -> str:
        if not self.history:
            return "- No prior events recorded."
        summary_lines = []
        for entry in self.history[-max_entries:]:
            role = entry.get("role", "assistant").title()
            content = " ".join(str(entry.get("content", "")).split())
            if len(content) > 140:
                content = content[:137].rstrip() + "..."
            summary_lines.append(f"- {role}: {content}")
        return "\n".join(summary_lines)

    def _dm_scene_context(self, prompt: str) -> str:
        turn_context = {
            "actor_name": self.world_state.get("player_name", "Player"),
            "actor_type": "player",
            "location": self.world_state.get("current_location") or self.world_state.get("location") or "Unknown",
            "objective": self.world_state.get("objective") or "No objective recorded.",
            "story_phase": self.world_state.get("story_phase") or "opening",
            "current_round": int(self.world_state.get("current_round", 1) or 1),
            "target_rounds": int(self.world_state.get("target_rounds", 0) or 0),
            "remaining_rounds": int(self.world_state.get("remaining_rounds", 0) or 0),
            "immediate_danger": self._immediate_danger_summary(),
            "scene_summary": self.world_state.get("scene_summary") or "No scene summary recorded yet.",
            "recent_party_actions": list(self.world_state.get("recent_party_actions", []))[-3:],
            "notable_npcs": self._world_state_list("notable_npcs")[:4],
            "nearby_locations": self._world_state_list("nearby_locations")[:4],
            "resolved_events": self._world_state_list("resolved_events")[-4:],
            "last_progress_events": self._world_state_list("last_progress_events")[-3:],
            "current_beat_goal": self._current_beat_goal(),
        }
        pending_roll = self.world_state.get("pending_roll")
        pending_roll_text = "none"
        if isinstance(pending_roll, dict):
            pending_roll_text = pending_roll.get("label", "pending roll")
        turn_context["phase_goal"] = phase_goal(turn_context["story_phase"], turn_context["remaining_rounds"])
        turn_context["scene_momentum"] = momentum_label(int(self.world_state.get("scene_stall_count", 0) or 0))
        return (
            "Current turn context:\n"
            f"{format_turn_context(turn_context)}\n"
            f"Submitted action: {prompt}\n"
            f"Pending roll: {pending_roll_text}\n"
            f"Arc pressure: {self._arc_pressure_instruction()}\n"
            f"Objective lock: {self._objective_lock_instruction()}"
        )

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
        progress_events = self._extract_tag_values(response, "progress", "id")
        resolve_events = self._extract_tag_values(response, "resolve", "id")
        ending_type = self._extract_ending_type(response)

        self.update_world_state("last_progress_events", progress_events + resolve_events)
        self._merge_unique_world_state_list("resolved_events", resolve_events)
        if ending_type:
            self._merge_unique_world_state_list("resolved_events", [f"ending_{ending_type}"])
            self.update_world_state("story_complete", True)
            self.update_world_state("ending_type", ending_type)
            self.update_world_state("current_beat", "resolution")
            self.update_world_state("story_phase", "resolution")

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
        cleaned = re.sub(r'\n?\s*<progress id="[^"]+"\s*/>\s*', "\n", cleaned)
        cleaned = re.sub(r'\n?\s*<resolve id="[^"]+"\s*/>\s*', "\n", cleaned)
        cleaned = re.sub(r'\n?\s*<ending type="[^"]+"\s*/>\s*', "\n", cleaned)
        return cleaned.strip()

    def _sanitize_dm_response(self, response: str, submitted_action: str) -> str:
        cleaned = response.strip()
        cleaned = re.sub(r"\bAssistant\s*\n", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?m)^\s*(?:Assistant|User|Narrator)\s*:.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?m)^\s*Outcome:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?m)^\s*(?:What do you do next\?|What action do you take\?)\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = self._truncate_after_follow_up(cleaned)
        cleaned = self._strip_follow_up_player_action(cleaned, submitted_action)
        cleaned = re.sub(r'(?m)^\s*"?What do you do next\?"?\s*$', "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return (
                "The situation shifts in response to your action, but the exact result is still unclear. "
                "A brief opening remains in front of you. What do you do next?"
            )
        in_resolution = self.world_state.get("story_phase") == "resolution" or self._response_declares_ending(response)
        if not in_resolution and not re.search(r"What do you do\??$", cleaned):
            cleaned = cleaned.rstrip(" .") + "\n\nWhat do you do next?"
        return cleaned

    def _extract_tag_values(self, response: str, tag_name: str, attribute: str) -> list[str]:
        pattern = re.compile(rf'<{tag_name}\s+{attribute}="([^"]+)"\s*/>')
        values = []
        for match in pattern.finditer(response):
            value = self._normalize_event_id(match.group(1))
            if value and value not in values:
                values.append(value)
        return values

    def _extract_ending_type(self, response: str) -> str | None:
        match = re.search(r'<ending type="([^"]+)"\s*/>', response)
        if not match:
            return None
        ending_type = match.group(1).strip().lower()
        if ending_type in _ENDING_TYPES:
            return ending_type
        return None

    def _response_declares_ending(self, response: str) -> bool:
        return self._extract_ending_type(response) is not None

    def _normalize_event_id(self, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized

    def _merge_unique_world_state_list(self, key: str, new_items: list[str]) -> list[str]:
        existing = self._world_state_list(key)
        for item in new_items:
            if item not in existing:
                existing.append(item)
        trimmed = existing[-12:]
        self.update_world_state(key, trimmed)
        return trimmed

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

    def _world_state_list(self, key: str) -> list[str]:
        value = self.world_state.get(key, [])
        if isinstance(value, list):
            return [str(entry).strip() for entry in value if str(entry).strip()]
        if value:
            return [str(value).strip()]
        return []

    def _immediate_danger_summary(self) -> str:
        pending_enemies = self._world_state_list("pending_encounter_enemies")
        if pending_enemies:
            return f"Hostile pressure from: {', '.join(pending_enemies[:4])}."
        pending_roll = self.world_state.get("pending_roll")
        if isinstance(pending_roll, dict):
            return f"Pending roll: {pending_roll.get('label', 'Resolve the requested roll.')}"
        return "No immediate danger recorded."

    def _current_beat_goal(self) -> str:
        """Return the goal for the current story beat."""
        story_arc = self.world_state.get("story_arc") or {}
        current_beat = str(self.world_state.get("current_beat", "hook") or "hook")
        beat_data = story_arc.get(current_beat) or {}
        return str(beat_data.get("goal", "") or "")

    def _arc_pressure_instruction(self) -> str:
        story_phase = str(self.world_state.get("story_phase", "opening") or "opening")
        remaining_rounds = int(self.world_state.get("remaining_rounds", 0) or 0)
        stall_count = int(self.world_state.get("scene_stall_count", 0) or 0)
        if remaining_rounds <= 2:
            return "FINAL SCENE: The story must conclude this turn. Force a decisive confrontation, escape, rescue, or resolution. Do not open new threads."
        if stall_count >= 3:
            return "SCENE STALLED: Do not repeat another cautious beat. Immediately introduce a threat, attack, forced reveal, or irreversible event that changes the situation."
        if stall_count >= 1:
            return "SLOW SCENE: Advance to a new clue, threat, or forced choice. Do not repeat the same cautious beat."
        if story_phase == "climax":
            return "CLIMAX NOW: Stop investigation. Force the main threat or conflict into direct contact with the party this turn — an attack, ambush, revelation, or irreversible event that demands immediate response."
        if story_phase == "resolution":
            return "RESOLUTION: End the main conflict this turn. Show the outcome and consequences. Do not open new plotlines or mysteries."
        if story_phase == "midgame":
            return "MIDGAME: Complicate the mission. Introduce a new obstacle, threat, or forced choice that escalates the stakes."
        return "OPENING: Pursue the hook and move toward the first concrete obstacle or threat."

    def _objective_lock_instruction(self) -> str:
        objective = str(self.world_state.get("objective", "") or "").strip()
        remaining_rounds = int(self.world_state.get("remaining_rounds", 0) or 0)
        if not objective:
            return "Keep the response tied to the clearest existing lead in the scene."
        if remaining_rounds <= 2:
            return f"Resolve or decisively answer this active objective now: {objective}"
        return f"Keep the response tied to this active objective and do not branch away from it: {objective}"

    def _truncate_after_follow_up(self, text: str) -> str:
        markers = [
            "\nAssistant\n",
            "\nWhat do you do next?\nOutcome:",
            "\nWhat action do you take?\nOutcome:",
            "\nOutcome:",
        ]
        end = len(text)
        for marker in markers:
            position = text.find(marker)
            if position != -1:
                end = min(end, position)
        return text[:end].strip()

    def _strip_follow_up_player_action(self, text: str, submitted_action: str) -> str:
        player_name = str(self.world_state.get("player_name") or "").strip()
        if not player_name:
            return text
        pattern = re.compile(
            rf"\b{re.escape(player_name)}\s*:\s*(.+?)(?=(?:\n[A-Z][a-zA-Z' -]+:|\n\*\*|\nWhat do you do next\?|$))",
            re.DOTALL,
        )
        kept_parts = []
        last_index = 0
        for match in pattern.finditer(text):
            spoken = " ".join(match.group(1).split())
            if self._is_same_action(spoken, submitted_action):
                continue
            kept_parts.append(text[last_index:match.start()])
            last_index = match.end()
        kept_parts.append(text[last_index:])
        return "".join(kept_parts).strip()

    def _is_same_action(self, generated_action: str, submitted_action: str) -> bool:
        generated = self._normalize_for_compare(generated_action)
        submitted = self._normalize_for_compare(submitted_action)
        if not generated or not submitted:
            return False
        if generated == submitted:
            return True
        return submitted in generated

    def _normalize_for_compare(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
        return " ".join(normalized.split())

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
