from dnd.ui import RESET, apply_base_style, highlight_quotes, thinking_message


def test_apply_base_style_reapplies_color_after_nested_reset(monkeypatch):
    monkeypatch.setattr("dnd.ui.color_enabled", lambda: True)

    styled = apply_base_style(f'plain {RESET}quoted{RESET} tail', "parchment")

    assert styled.count("\033[38;5;230m") >= 3
    assert styled.endswith(RESET)


def test_thinking_message_uses_dim_italic_silver(monkeypatch):
    monkeypatch.setattr("dnd.ui.color_enabled", lambda: True)

    styled = thinking_message("DM is thinking")

    assert "\033[2m" in styled
    assert "\033[3m" in styled
    assert "\033[38;5;252m" in styled
    assert "<DM is thinking...>" in styled


def test_highlight_quotes_applies_quote_color(monkeypatch):
    monkeypatch.setattr("dnd.ui.color_enabled", lambda: True)

    styled = highlight_quotes('Bram says, "Something is wrong."')

    assert "\033[38;5;186m" in styled
    assert '"Something is wrong."' in styled


def test_highlight_quotes_handles_wrapped_multiline_quotes(monkeypatch):
    monkeypatch.setattr("dnd.ui.color_enabled", lambda: True)

    styled = highlight_quotes('"We need to find Elara and any survivors.\nLet\'s split up and cover more ground."')

    assert "\033[38;5;186m" in styled
    assert 'We need to find Elara and any survivors.\nLet\'s split up and cover more ground.' in styled
