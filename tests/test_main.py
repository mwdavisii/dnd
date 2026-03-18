import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from datetime import datetime
import pytest
from dnd.spectator import build_turn_context, detect_scene_stall, extract_open_threads, validate_turn_output

from main import (
    choose_save_file,
    create_transcript_path,
    derive_story_phase,
    run_between_quest_menu,
    run_initial_setup,
    run_level_up_menu,
    should_wait_before_spectator_turn,

)


def test_choose_save_file_prompts_for_name_when_no_saves(monkeypatch, tmp_path):
    monkeypatch.setattr("main.list_save_files", lambda: [])
    inputs = iter(["my_adventure"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("main.create_save_path", lambda name=None: str(tmp_path / f"{name}.db"))
    result = choose_save_file()
    assert "my_adventure" in result


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




def test_extract_open_threads_parses_summary():
    summary = (
        "EVENTS SO FAR:\n"
        "- Party arrived in Ashford\n"
        "- Met Elric at the tavern\n\n"
        "OPEN THREADS:\n"
        "- Missing trader last seen near old mill\n"
        "- Hooded figure spotted at tavern\n\n"
        "ESCALATION LEVEL: Rising tension."
    )
    result = extract_open_threads(summary)
    assert "Missing trader" in result
    assert "Hooded figure" in result
    assert "EVENTS SO FAR" not in result
    assert "ESCALATION LEVEL" not in result


def test_extract_open_threads_returns_empty_on_missing_section():
    summary = "EVENTS SO FAR:\n- Something happened\n\nESCALATION LEVEL: Low."
    result = extract_open_threads(summary)
    assert result == ""


def test_build_turn_context_includes_story_summary():
    context = build_turn_context(
        {
            "location": "Ashford",
            "objective": "Investigate.",
            "story_phase": "opening",
            "current_round": 1,
            "target_rounds": 10,
            "remaining_rounds": 9,
            "story_summary": "EVENTS SO FAR:\n- Arrived in Ashford\n\nOPEN THREADS:\n- Letter\n\nESCALATION LEVEL: Low.",
        },
        actor_name="Kraton",
        actor_type="player",
        scene_summary="The square is quiet.",
    )
    assert context["story_summary"] == "EVENTS SO FAR:\n- Arrived in Ashford\n\nOPEN THREADS:\n- Letter\n\nESCALATION LEVEL: Low."


def test_build_turn_context_uses_structured_world_state():
    context = build_turn_context(
        {
            "location": "Willowmere",
            "objective": "Question the guard and inspect the forge.",
            "story_phase": "opening",
            "current_round": 3,
            "target_rounds": 10,
            "remaining_rounds": 7,
            "notable_npcs": ["Guard", "Elara"],
            "nearby_locations": ["Forge", "Alehouse"],
            "last_progress_events": ["goblin_revealed"],
        },
        actor_name="Kraton",
        actor_type="player",
        scene_summary="The square is tense.",
        recent_party_actions=["Lyra acted: I circle the forge."],
    )

    assert context["location"] == "Willowmere"
    assert context["objective"] == "Question the guard and inspect the forge."
    assert context["current_round"] == 3
    assert context["recent_party_actions"] == ["Lyra acted: I circle the forge."]
    assert context["last_progress_events"] == ["goblin_revealed"]
    assert "question" in context["focus_keywords"] or "guard" in context["focus_keywords"]


def test_validate_turn_output_rejects_recent_duplicates():
    action = validate_turn_output(
        "I circle the forge.",
        actor_name="Kraton",
        actor_type="player",
        recent_party_actions=["Kraton acted: I circle the forge."],
    )

    from dnd.spectator import is_fallback_action
    assert is_fallback_action(action)  # should be a fallback, not the duplicate
    assert "circle" not in action.lower()  # should NOT be the original duplicate


def test_validate_turn_output_rejects_action_that_abandons_active_hook():
    turn_context = build_turn_context(
        {
            "objective": "Follow the cloaked man before he leaves town.",
            "story_phase": "opening",
            "current_round": 1,
            "target_rounds": 10,
            "remaining_rounds": 9,
            "nearby_locations": ["Inn", "Town edge"],
            "notable_npcs": ["Cloaked man"],
        },
        actor_name="Kraton",
        actor_type="player",
        scene_summary="A cloaked man hurries toward the edge of town.",
        recent_party_actions=[],
    )

    action = validate_turn_output(
        "Inspect a dusty old book in a nearby shop window.",
        actor_name="Kraton",
        actor_type="player",
        recent_party_actions=[],
        turn_context=turn_context,
    )

    assert "main lead" in action.lower() or "town edge" in action.lower()


def test_validate_turn_output_rejects_fuzzy_duplicate():
    from dnd.spectator import is_fallback_action

    action = validate_turn_output(
        "I raise my shield and stand firm, blocking the path.",
        actor_name="Garrick",
        actor_type="companion",
        recent_party_actions=["Garrick acted: I raise my shield, standing firm to block the path."],
    )
    assert is_fallback_action(action)


def test_validate_turn_output_allows_genuinely_different_action():
    from dnd.spectator import is_fallback_action

    action = validate_turn_output(
        "I slip behind the figure and search for a back entrance to the mill.",
        actor_name="Lyra",
        actor_type="companion",
        recent_party_actions=["Garrick acted: I raise my shield, standing firm to block the path."],
    )
    assert not is_fallback_action(action)
    assert "slip behind" in action.lower()


def test_detect_scene_stall_flags_near_duplicate_without_progress():
    stalled = detect_scene_stall(
        "Last turn: take a cautious step forward Consequences: The shadows stir near the clearing.",
        "Last turn: take another cautious step forward Consequences: The shadows stir near the clearing.",
        [],
    )

    assert stalled is True


def test_detect_scene_stall_uses_open_threads_from_summary():
    # Scene summaries differ (below 55% overlap) but threads are identical
    stalled = detect_scene_stall(
        "Last turn: demand answers Consequences: The figure refuses.",
        "Last turn: threaten the figure Consequences: They hold their ground.",
        [],
        previous_threads="- Cloaked figure blocking the mill entrance",
        current_threads="- Cloaked figure blocking the mill entrance",
    )
    assert stalled is True


def test_detect_scene_stall_not_stalled_when_threads_change():
    stalled = detect_scene_stall(
        "Last turn: demand answers Consequences: The figure refuses.",
        "Last turn: push past the figure Consequences: You enter the mill.",
        [],
        previous_threads="- Cloaked figure blocking the mill entrance",
        current_threads="- Inside the mill, bandits spotted",
    )
    assert stalled is False


def test_detect_scene_stall_backward_compatible_without_threads():
    # Existing behavior works when threads are not provided
    stalled = detect_scene_stall(
        "Last turn: take a cautious step forward Consequences: The shadows stir near the clearing.",
        "Last turn: take another cautious step forward Consequences: The shadows stir near the clearing.",
        [],
    )
    assert stalled is True


def test_detect_scene_stall_allows_progress_events():
    stalled = detect_scene_stall(
        "Last turn: question Eli Consequences: He warns that the mayor was taken.",
        "Last turn: push toward the gate Consequences: A goblin horn sounds from the battlements.",
        ["mayor_warned"],
    )

    assert stalled is False


def test_transcript_writer_receives_dm_response(monkeypatch, tmp_path):
    """TranscriptWriter.write_dm_response is called with cleaned text and elapsed."""
    from unittest.mock import MagicMock, patch
    import main as main_module
    from dnd.transcript import TranscriptWriter

    transcript = MagicMock(spec=TranscriptWriter)

    fake_dm = MagicMock()
    fake_dm.generate_response.return_value = (
        "Raw response with <level_up />",
        "Cleaned response without tags.",
    )
    fake_dm.world_state = {
        "scene_summary": "",
        "recent_party_actions": [],
        "last_progress_events": [],
        "reward_history": [],
    }

    fake_player = MagicMock()
    fake_player.name = "Kraton"

    fake_handler = MagicMock()

    with patch("main.build_scene_memory", return_value="scene"):
        with patch("main.detect_scene_stall", return_value=False):
            main_module.process_dm_turn(
                "Look around.",
                fake_dm,
                {},
                fake_player,
                {},
                fake_handler,
                transcript=transcript,
            )

    transcript.write_dm_response.assert_called_once()
    args = transcript.write_dm_response.call_args
    assert "Cleaned response without tags." in args[0][0]
    assert isinstance(args[0][1], float)  # elapsed


def test_process_dm_turn_returns_story_completion(monkeypatch):
    from unittest.mock import MagicMock
    import main as main_module

    fake_dm = MagicMock()
    fake_dm.generate_response.return_value = (
        'The sigil breaks.\n<ending type="victory" />',
        "The sigil breaks.",
    )
    fake_dm.world_state = {
        "scene_summary": "",
        "recent_party_actions": [],
        "last_progress_events": ["ritual_stopped"],
        "reward_history": [],
    }
    fake_dm.story_is_complete.return_value = True

    fake_player = MagicMock()
    fake_player.name = "Kraton"

    fake_handler = MagicMock()

    monkeypatch.setattr(main_module, "build_scene_memory", lambda *_args, **_kwargs: "scene")
    monkeypatch.setattr(main_module, "detect_scene_stall", lambda *_args, **_kwargs: False)

    story_complete = main_module.process_dm_turn(
        "Look around.",
        fake_dm,
        {},
        fake_player,
        {},
        fake_handler,
        transcript=None,
    )

    assert story_complete is True


def test_process_dm_turn_passes_threads_to_stall_detection(monkeypatch):
    from unittest.mock import MagicMock, patch, call
    import main as main_module

    fake_dm = MagicMock()
    fake_dm.generate_response.return_value = (
        "The figure blocks your path again.",
        "The figure blocks your path again.",
    )
    fake_dm.world_state = {
        "scene_summary": "Previous scene.",
        "recent_party_actions": [],
        "last_progress_events": [],
        "reward_history": [],
        "scene_stall_count": 0,
        "story_summary": (
            "EVENTS SO FAR:\n- Arrived at mill\n\n"
            "OPEN THREADS:\n- Cloaked figure blocking entrance\n\n"
            "ESCALATION LEVEL: Medium."
        ),
        "previous_open_threads": "- Cloaked figure blocking entrance",
    }
    fake_dm.story_is_complete.return_value = False

    fake_player = MagicMock()
    fake_player.name = "Kraton"

    fake_handler = MagicMock()

    captured_stall_args = {}

    original_detect = main_module.detect_scene_stall

    def spy_detect(*args, **kwargs):
        captured_stall_args.update(kwargs)
        return original_detect(*args, **kwargs)

    monkeypatch.setattr(main_module, "build_scene_memory", lambda *_args, **_kwargs: "scene")
    monkeypatch.setattr(main_module, "detect_scene_stall", spy_detect)

    main_module.process_dm_turn("Step aside.", fake_dm, {}, fake_player, {}, fake_handler)

    assert "current_threads" in captured_stall_args or "previous_threads" in captured_stall_args


def test_run_level_up_menu_calls_level_up_with_rolled_hp(monkeypatch):
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 2}
    player_sheet.class_name = "Cleric"
    player_sheet.spells = []

    with patch("main.roll_dice", return_value=(6, "1d8 → 6")):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_level_up_menu(player_sheet)

    # HP = roll(6) + CON mod(2) = 8, min 1
    player_sheet.level_up.assert_called_once_with(8)


def test_run_level_up_menu_minimum_hp_increase_is_1(monkeypatch):
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d6"
    player_sheet.ability_modifiers = {"CON": -3}
    player_sheet.class_name = "Wizard"
    player_sheet.spells = []

    with patch("main.roll_dice", return_value=(1, "1d6 → 1")):
        monkeypatch.setattr("builtins.input", lambda _: "")
        run_level_up_menu(player_sheet)

    # HP = roll(1) + CON(-3) = -2, clamped to 1
    player_sheet.level_up.assert_called_once_with(1)


def test_run_level_up_menu_spell_selection_for_caster(monkeypatch):
    """A caster class with learnable spells shows the selection prompt."""
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 0}
    player_sheet.class_name = "Bard"
    # Bard starts with Cure Wounds; Thunderwave is available but not yet known
    player_sheet.spells = [{"name": "Cure Wounds"}]

    inputs = iter(["1"])  # pick first available spell
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.roll_dice", return_value=(4, "1d8 → 4")):
        run_level_up_menu(player_sheet)

    player_sheet.learn_spell.assert_called_once()


def test_run_level_up_menu_skip_spell_selection(monkeypatch):
    """Choosing 0 skips spell learning."""
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 0}
    player_sheet.class_name = "Bard"
    player_sheet.spells = []

    inputs = iter(["0"])  # skip spell
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.roll_dice", return_value=(4, "1d8 → 4")):
        run_level_up_menu(player_sheet)

    player_sheet.learn_spell.assert_not_called()


@pytest.mark.ollama
@pytest.mark.skipif(
    not os.getenv("OLLAMA_HOST") or not os.getenv("OLLAMA_MODEL"),
    reason="requires a configured Ollama server and model",
)
def test_main_executes_short_spectator_game_with_two_npcs(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    scripted_input = "\n".join(
        [
            "n",      # no transcript
            "2",      # spectator mode
            "1",      # short session (10 rounds)
            "0.01",   # spectator autoplay
            "Kraton",
            "",
            "",
            "10",     # Sorcerer
            "3",      # Sage
            "1",      # +2/+1
            "INT",
            "WIS",
            "",       # begin adventure
            "2",      # two companions
        ]
    ) + "\n"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env.setdefault("TERM", "dumb")

    result = subprocess.run(
        [sys.executable, str(repo_root / "main.py")],
        input=scripted_input,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=240,
        check=False,
    )

    if "Operation not permitted" in result.stderr and "localhost" in result.stderr:
        pytest.skip("sandbox blocked the subprocess from connecting to local Ollama")

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Spectator mode is on" in result.stdout
    assert "Spectator run finished: reached the configured round limit." in result.stdout

    save_files = list((tmp_path / "saves").glob("*.db"))
    assert len(save_files) == 1

    conn = sqlite3.connect(save_files[0])
    player_count = conn.execute("SELECT COUNT(*) FROM characters WHERE is_player = 1").fetchone()[0]
    npc_count = conn.execute("SELECT COUNT(*) FROM characters WHERE is_player = 0").fetchone()[0]
    conn.close()

    assert player_count == 1
    assert npc_count == 2


def test_run_between_quest_menu_rest_yes(monkeypatch):
    from unittest.mock import MagicMock
    player_sheet = MagicMock()
    player_sheet.spells = []
    handler = MagicMock()

    inputs = iter(["y", "n", ""])  # rest=yes, shop=no, press enter
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    run_between_quest_menu(player_sheet, handler, level_eligible=False)

    player_sheet.take_long_rest.assert_called_once()
    handler.handle.assert_not_called()


def test_run_between_quest_menu_shop_buy_loop(monkeypatch):
    from unittest.mock import MagicMock
    player_sheet = MagicMock()
    player_sheet.spells = []
    handler = MagicMock()
    handler.handle.return_value = (True, "")

    inputs = iter(["n", "y", "/buy Healing Potion", "done", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    run_between_quest_menu(player_sheet, handler, level_eligible=False)

    player_sheet.take_long_rest.assert_not_called()
    handler.handle.assert_any_call("/shop")
    handler.handle.assert_any_call("/buy Healing Potion")


def test_run_between_quest_menu_triggers_level_up_when_eligible(monkeypatch):
    from unittest.mock import patch, MagicMock
    player_sheet = MagicMock()
    player_sheet.level = 1
    player_sheet.hit_die_type = "d8"
    player_sheet.ability_modifiers = {"CON": 0}
    player_sheet.class_name = "Fighter"
    player_sheet.spells = []
    handler = MagicMock()

    inputs = iter(["n", "n", ""])  # no rest, no shop, press enter
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch("main.roll_dice", return_value=(5, "1d8 → 5")):
        run_between_quest_menu(player_sheet, handler, level_eligible=True)

    player_sheet.level_up.assert_called_once_with(5)
