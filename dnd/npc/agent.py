# dnd/npc/agent.py
import os
import requests
import json
from dotenv import load_dotenv
from dnd.database import load_npc_memories, save_npc_memory
from dnd.ui import thinking_message, wrap_text

load_dotenv()

class NPCAgent:
    def __init__(self, name: str, class_name: str, system_prompt: str, session_id: int):
        self.session_id = session_id
        self.name = name
        self.class_name = class_name
        self.system_prompt = system_prompt
        self.history = []
        self.memory = load_npc_memories(session_id, name)
        self.ollama_host = os.getenv("OLLAMA_HOST")
        self.ollama_model = os.getenv("OLLAMA_MODEL")
        if not self.ollama_host or not self.ollama_model:
            raise ValueError("OLLAMA_HOST and OLLAMA_MODEL must be set in .env file")

    def generate_response(self, prompt: str, game_context: list) -> str:
        self.history.append({"role": "user", "content": prompt})
        self.remember(f"Player asked {self.name}: {prompt}")
        
        full_prompt = (
            f"{self.system_prompt}\n\n"
            "What you distinctly remember:\n"
            f"{self._format_memory()}\n\n"
            "Your recent direct conversations:\n"
            f"{self._format_history(self.history[-6:])}\n\n"
            "You are in a party of adventurers. Here is the story so far:\n"
            f"{self._format_history(game_context)}\n\n"
            f"You are now being asked directly: {prompt}\n\n"
            "Reply directly to the player in 1-3 short sentences.\n"
            "Be concrete and useful. Prefer one recommendation or one warning.\n"
            "Do not narrate scene changes. Do not address other companions unless necessary.\n"
            "Do not end with filler, speeches, or party banter.\n"
            "What is your response?"
        )

        try:
            print(thinking_message(f"{self.name} is thinking"))
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": full_prompt,
                    "system": self.system_prompt,
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
            self.history.append({"role": "assistant", "content": final_response})
            self.remember(f"{self.name} said: {final_response}")
            print(wrap_text(final_response))
            return final_response

        except requests.exceptions.RequestException as e:
            error_message = f"Error connecting to Ollama: {e}"
            print(error_message)
            return error_message

    def generate_turn_action(self, game_context: list, scene_summary: str, recent_party_actions: list[str] | None = None) -> str:
        party_actions = recent_party_actions or []
        prompt = (
            f"{self.system_prompt}\n\n"
            "What you distinctly remember:\n"
            f"{self._format_memory()}\n\n"
            "Here is the current scene summary:\n"
            f"{scene_summary}\n\n"
            "Recent party actions:\n"
            f"{self._format_party_actions(party_actions)}\n\n"
            "Here is the recent party history:\n"
            f"{self._format_history(game_context[-8:])}\n\n"
            f"It is {self.name}'s turn.\n"
            "In 1-2 short sentences, describe only your own action, movement, warning, or observation.\n"
            "Coordinate with recent ally actions when it makes sense.\n"
            "Do not narrate the player's actions. Do not command the player to cast, attack, or move.\n"
            "Do not speak for other companions. Stay concrete and brief."
        )

        try:
            print(thinking_message(f"{self.name} is thinking"))
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "system": self.system_prompt,
                    "stream": False,
                },
                timeout=(5, 120),
            )
            response.raise_for_status()
            payload = response.json()
            final_response = payload.get("response", "").strip()
            if final_response:
                self.history.append({"role": "assistant", "content": final_response})
                self.remember(f"{self.name} took a turn: {final_response}")
            return final_response
        except requests.exceptions.RequestException as e:
            error_message = f"Error connecting to Ollama: {e}"
            print(error_message)
            return error_message

    def _format_history(self, history):
        return "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in history])

    def remember(self, memory: str):
        memory = memory.strip()
        if not memory:
            return
        if memory in self.memory:
            return
        self.memory.append(memory)
        self.memory = self.memory[-12:]
        save_npc_memory(self.session_id, self.name, memory)

    def remember_scene(self, scene_summary: str):
        self.remember(f"Scene memory: {scene_summary}")

    def _format_memory(self):
        if not self.memory:
            return "- No strong memories yet."
        return "\n".join(f"- {entry}" for entry in self.memory[-8:])

    def _format_party_actions(self, actions: list[str]) -> str:
        if not actions:
            return "- No recent party actions recorded."
        return "\n".join(f"- {action}" for action in actions[-3:])
