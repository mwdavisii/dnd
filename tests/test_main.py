from pathlib import Path

from datetime import datetime

from main import (
    choose_save_file,
    create_transcript_path,
    derive_story_phase,
    run_initial_setup,
    should_wait_before_spectator_turn,
    strip_ansi,
)


def test_choose_save_file_shows_created_and_last_played(monkeypatch, capsys, tmp_path):
    save_path = tmp_path / "campaign.db"
    save_path.touch()

    monkeypatch.setattr("main.clear_screen", lambda: None)
    monkeypatch.setattr("main.banner", lambda text: text)
    monkeypatch.setattr("main.prompt_marker", lambda: ">")
    monkeypatch.setattr("main.style", lambda text, *_args, **_kwargs: text)
    monkeypatch.setattr("main.list_save_files", lambda: [Path(save_path)])
    monkeypatch.setattr("main.format_save_label", lambda _path: "campaign")
    monkeypatch.setattr(
        "main.get_save_metadata",
        lambda _path: {"created_at": "2026-03-12 07:00 PM", "last_accessed_at": "2026-03-13 08:15 AM"},
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "1")

    selected = choose_save_file()

    out = capsys.readouterr().out
    assert selected == str(save_path)
    assert "Created:" in out
    assert "2026-03-12 07:00 PM" in out
    assert "Last Played:" in out
    assert "2026-03-13 08:15 AM" in out


def test_opening_scene_rendering_can_highlight_quotes(monkeypatch):
    monkeypatch.setattr("dnd.ui.color_enabled", lambda: True)

    from dnd.ui import apply_base_style, highlight_quotes, wrap_text

    rendered = apply_base_style(highlight_quotes(wrap_text('Bram says, "Something is wrong."')), "parchment")

    assert "\033[38;5;186m" in rendered
    assert '"Something is wrong."' in rendered


def test_run_initial_setup_returns_expected_tuple(monkeypatch):
    monkeypatch.setattr("main.choose_game_mode", lambda: True)
    monkeypatch.setattr("main.choose_session_round_budget", lambda: 12)
    monkeypatch.setattr("main.choose_spectator_settings", lambda: 1.5)
    monkeypatch.setattr("main.run_character_creation", lambda: "Aster")
    seeded = {}
    monkeypatch.setattr("main.choose_companion_count", lambda _max_count: 2)
    monkeypatch.setattr("main.seed_npcs", lambda count: seeded.setdefault("count", count))

    result = run_initial_setup()

    assert result == (True, 12, 1.5, "Aster")
    assert seeded["count"] == 2


def test_should_wait_before_spectator_turn_skips_player_turns():
    assert should_wait_before_spectator_turn("player") is False
    assert should_wait_before_spectator_turn("companion") is True
    assert should_wait_before_spectator_turn("enemy") is True


def test_derive_story_phase_uses_round_budget():
    assert derive_story_phase(1, 20) == "opening"
    assert derive_story_phase(8, 20) == "midgame"
    assert derive_story_phase(16, 20) == "climax"
    assert derive_story_phase(19, 20) == "resolution"


def test_create_transcript_path_uses_markdown_and_save_label():
    transcript_path = create_transcript_path("/tmp/my_campaign.db", now=datetime(2026, 3, 13, 9, 45, 0))

    assert transcript_path == Path("logs/my_campaign_20260313_094500.md")


def test_strip_ansi_removes_terminal_sequences():
    assert strip_ansi("\033[31mDanger\033[0m") == "Danger"
