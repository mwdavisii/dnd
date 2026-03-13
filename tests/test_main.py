from pathlib import Path

from main import choose_save_file


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
