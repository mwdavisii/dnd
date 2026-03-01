# dnd/npc/agent.py
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

class NPCAgent:
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.history = [] # This will store direct interactions with the NPC
        self.ollama_host = os.getenv("OLLAMA_HOST")
        self.ollama_model = os.getenv("OLLAMA_MODEL")

    def generate_response(self, prompt: str, game_context: list) -> str:
        self.history.append({"role": "user", "content": prompt})
        
        # We give the NPC its personality, the context of the whole game, and the specific question.
        full_prompt = (
            f"{self.system_prompt}\n\n"
            "You are in a party of adventurers. Here is the story so far:\n"
            f"{self._format_history(game_context)}\n\n"
            f"You are now being asked directly: {prompt}\n\n"
            "What is your response?"
        )

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": full_prompt,
                    "system": self.system_prompt,
                    "stream": True,
                },
                stream=True
            )
            response.raise_for_status()

            full_response = []
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    json_line = json.loads(decoded_line)
                    if not json_line.get('done', False):
                        response_part = json_line.get('response', '')
                        print(response_part, end='', flush=True)
                        full_response.append(response_part)

            final_response = "".join(full_response)
            self.history.append({"role": "assistant", "content": final_response})
            print() # for a newline after the streaming response
            return final_response

        except requests.exceptions.RequestException as e:
            error_message = f"Error connecting to Ollama: {e}"
            print(error_message)
            return error_message

    def _format_history(self, history):
        return "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in history])

