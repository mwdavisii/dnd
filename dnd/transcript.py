from datetime import datetime
from pathlib import Path


class TranscriptWriter:
    """Writes a clean structured markdown transcript of a game session."""

    def __init__(self, path: Path, save_path: str, model: str):
        self.path = path
        self.save_path = save_path
        self.model = model
        self._file = None

    def start(self) -> "TranscriptWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        save_label = Path(self.save_path).stem
        started = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        self._file.write("# D&D Session Transcript\n\n")
        self._file.write("| | |\n|---|---|\n")
        self._file.write(f"| Save | `{save_label}` |\n")
        self._file.write(f"| Started | {started} |\n")
        self._file.write(f"| Model | `{self.model}` |\n\n")
        self._file.write("---\n\n")
        self._file.flush()
        return self

    def stop(self):
        if self._file:
            self._file.close()
            self._file = None

    def write_opening_scene(self, text: str, elapsed: float):
        self._write(f"## Opening Scene *({elapsed:.1f}s)*\n\n{text}\n\n---\n\n")

    def write_round_header(self, round_number: int):
        self._write(f"## Round {round_number}\n\n")

    def write_player_action(self, actor_name: str, action: str):
        self._write(f"### {actor_name} — Player\n\n> {action}\n\n")

    def write_companion_action(self, actor_name: str, action: str):
        self._write(f"### {actor_name} — Companion\n\n> {action}\n\n---\n\n")

    def write_dm_response(self, text: str, elapsed: float):
        self._write(f"### Dungeon Master *({elapsed:.1f}s)*\n\n{text}\n\n---\n\n")

    def _write(self, content: str):
        if self._file:
            self._file.write(content)
            self._file.flush()
