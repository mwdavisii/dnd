import pytest
from pathlib import Path
from dnd.transcript import TranscriptWriter


def test_transcript_writer_creates_header(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.stop()

    content = path.read_text()
    assert "# D&D Session Transcript" in content
    assert "my_save" in content
    assert "llama3" in content


def test_transcript_writer_opening_scene(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_opening_scene("You stand in a market square.", elapsed=3.2)
    writer.stop()

    content = path.read_text()
    assert "## Opening Scene" in content
    assert "3.2s" in content
    assert "You stand in a market square." in content


def test_transcript_writer_round_header(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_round_header(3)
    writer.stop()

    content = path.read_text()
    assert "## Round 3" in content


def test_transcript_writer_player_action(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_player_action("Kraton", "Follow the cloaked man.")
    writer.stop()

    content = path.read_text()
    assert "### Kraton" in content
    assert "Player" in content
    assert "> Follow the cloaked man." in content


def test_transcript_writer_companion_action(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_companion_action("Kaelen", "I cover the exit.")
    writer.stop()

    content = path.read_text()
    assert "### Kaelen" in content
    assert "Companion" in content
    assert "> I cover the exit." in content


def test_transcript_writer_dm_response(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.write_dm_response("The figure vanishes into an alley.", elapsed=4.1)
    writer.stop()

    content = path.read_text()
    assert "### Dungeon Master" in content
    assert "4.1s" in content
    assert "The figure vanishes into an alley." in content


def test_transcript_writer_stop_is_safe_when_not_started(tmp_path):
    path = tmp_path / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.stop()  # Should not raise


def test_transcript_writer_creates_parent_dirs(tmp_path):
    path = tmp_path / "logs" / "nested" / "run.md"
    writer = TranscriptWriter(path=path, save_path="saves/my_save.db", model="llama3")
    writer.start()
    writer.stop()
    assert path.exists()
