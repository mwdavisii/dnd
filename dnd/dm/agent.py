import os
import requests
import json
from dotenv import load_dotenv
from dnd.dm.prompts import SYSTEM_PROMPT
from dnd.character import CharacterSheet

load_dotenv()

class DungeonMaster:
    def __init__(self):
        self.history = []
        self.ollama_host = os.getenv("OLLAMA_HOST")
        self.ollama_model = os.getenv("OLLAMA_MODEL")
        if not self.ollama_host or not self.ollama_model:
            raise ValueError("OLLAMA_HOST and OLLAMA_MODEL must be set in .env file")

    def generate_response(self, prompt: str, player_sheet: CharacterSheet) -> str:
        self.history.append({"role": "user", "content": prompt})
        
        full_prompt = (
            f"{player_sheet.get_prompt_summary()}\n\n"
            "Here is the story so far:\n"
            f"{self._format_history()}"
        )

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": full_prompt,
                    "system": SYSTEM_PROMPT,
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

    def _format_history(self):
        return "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in self.history])


