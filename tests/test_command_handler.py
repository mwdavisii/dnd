# tests/test_command_handler.py
import pytest
from unittest.mock import MagicMock, patch
from dnd.cli import CommandHandler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def player_sheet():
    sheet = MagicMock()
    sheet.name = "Wizard"
    sheet.class_name = "Wizard"
    sheet.initiative = 2
    sheet.gold = 100
    sheet.ability_modifiers = {"STR": -1, "DEX": 3, "CON": 1, "INT": 3, "WIS": 0, "CHA": 1}
    sheet.get_saving_throw_modifier.side_effect = lambda ability: {"STR": 0, "DEX": 5, "CON": 1, "INT": 3, "WIS": 0, "CHA": 1}[ability]
    sheet.spells = [
        {'name': 'Fire Bolt', 'level': 0},
        {'name': 'Magic Missile', 'level': 1},
    ]
    sheet.inventory_items = [('Dagger', 1), ('Spellbook', 1)]
    sheet.equipped_items = []
    sheet.unequipped_items = ['Dagger', 'Spellbook']
    sheet.get_attack_breakdown.return_value = {
        "weapon_name": "Dagger",
        "ability_name": "DEX",
        "ability_mod": 3,
        "is_proficient": True,
        "proficiency_bonus": 2,
        "poisoned_penalty": 0,
        "total_attack_bonus": 5,
        "base_damage_die": "1d4",
        "damage_type": "Piercing",
        "damage_modifier": 3,
        "rage_damage": 0,
        "sneak_attack_damage": None,
    }
    sheet.get_spellcasting_breakdown.return_value = {
        "spell_name": "Magic Missile",
        "level": 1,
        "ability_name": "INT",
        "ability_mod": 3,
        "proficiency_bonus": 2,
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "range": "120 feet",
        "casting_time": "1 action",
        "duration": "Instantaneous",
        "slots_current": 2,
        "slots_max": 2,
    }
    sheet._id = 1
    return sheet


@pytest.fixture
def dm():
    mock_dm = MagicMock()
    mock_dm.history = []
    mock_dm.world_state = {
        'location': 'tavern',
        'region': 'Greenfields',
        'objective': 'Find the missing caravan',
        'quests': ['Investigate the old road', 'Question the innkeeper'],
        'discoveries': ['Fresh wagon tracks outside town'],
        'notable_npcs': ['Innkeeper Mara'],
        'nearby_locations': ['Old road', 'Town square'],
        'exits': ['north to the old road', 'east to the stables'],
    }
    return mock_dm


@pytest.fixture
def handler(player_sheet, dm):
    character_sheets = {'wizard': player_sheet}
    return CommandHandler(player_sheet, character_sheets, npcs={}, dm=dm)


# ---------------------------------------------------------------------------
# /roll
# ---------------------------------------------------------------------------

def test_roll_skips_dm(handler):
    with patch('dnd.cli.roll_dice', return_value=(15, "Rolled 1d20: 15")):
        skip_dm, result = handler.handle("/roll 1d20")
    assert skip_dm is True
    assert result == ""


def test_roll_invalid_skips_dm(handler):
    with patch('dnd.cli.roll_dice', side_effect=ValueError("bad dice")):
        skip_dm, result = handler.handle("/roll bad")
    assert skip_dm is True


def test_roll_uses_pending_roll_when_no_args(handler, dm, capsys):
    dm.world_state["pending_roll"] = {"type": "save", "ability": "DEX", "label": "Dexterity saving throw"}
    with patch('dnd.cli.roll_dice', return_value=(12, "Rolling 1d20: (12) = 12")):
        skip_dm, result = handler.handle("/roll")
    assert skip_dm is True
    assert result == ""
    out = capsys.readouterr().out
    assert "Dexterity saving throw:" in out
    assert "Rolling 1d20: (12) = 12 + 5 = 17" in out
    dm.update_world_state.assert_called_with("pending_roll", None)


def test_roll_supports_ability_shortcut(handler, dm, capsys):
    with patch('dnd.cli.roll_dice', return_value=(10, "Rolling 1d20: (10) = 10")):
        skip_dm, result = handler.handle("/roll dex")
    assert skip_dm is True
    assert result == ""
    out = capsys.readouterr().out
    assert "DEX check:" in out
    assert "Rolling 1d20: (10) = 10 + 3 = 13" in out


def test_roll_supports_save_shortcut(handler, dm, capsys):
    with patch('dnd.cli.roll_dice', return_value=(11, "Rolling 1d20: (11) = 11")):
        skip_dm, result = handler.handle("/roll dex save")
    assert skip_dm is True
    assert result == ""
    out = capsys.readouterr().out
    assert "DEX saving throw:" in out
    assert "Rolling 1d20: (11) = 11 + 5 = 16" in out


# ---------------------------------------------------------------------------
# /attack
# ---------------------------------------------------------------------------

def test_attack_shows_breakdown(handler, capsys):
    skip_dm, result = handler.handle("/attack Dagger")
    assert skip_dm is False
    assert result == "I attack with my Dagger."
    out = capsys.readouterr().out
    assert "Attacking with Dagger" in out
    assert "To Hit: 1d20 + DEX mod (+3) + proficiency (+2) = +5" in out
    assert "Damage: 1d4 + +3 Piercing" in out


def test_attack_with_teaching_mode(handler, capsys):
    handler.handle("/teach on")
    skip_dm, _ = handler.handle("/attack Dagger")
    assert skip_dm is False
    out = capsys.readouterr().out
    assert "Teaching mode is on." in out
    assert "Teaching: Roll the d20 and add the total to-hit bonus." in out


def test_attack_rejected_when_not_player_turn(player_sheet, dm, capsys):
    npc = MagicMock()
    npc.name = "Bram"
    npc_sheet = MagicMock()
    npc_sheet.initiative = 1
    h = CommandHandler(player_sheet, {"wizard": player_sheet, "bram": npc_sheet}, npcs={"bram": npc}, dm=dm)
    h.advance_turn()
    skip_dm, result = h.handle("/attack Dagger")
    assert skip_dm is True
    assert result == ""
    out = capsys.readouterr().out
    assert "It is currently Bram's turn, not yours." in out


def test_player_can_act_false_when_companion_turn(player_sheet, dm, capsys):
    npc = MagicMock()
    npc.name = "Lyra"
    npc_sheet = MagicMock()
    npc_sheet.initiative = 1
    h = CommandHandler(player_sheet, {"wizard": player_sheet, "lyra": npc_sheet}, npcs={"lyra": npc}, dm=dm)
    h.advance_turn()
    assert h.player_can_act() is False
    assert "It is currently Lyra's turn, not yours." in capsys.readouterr().out


def test_attack_auto_starts_pending_encounter(handler, dm, capsys):
    dm.world_state["pending_encounter_enemies"] = ["Goblin"]
    with patch('dnd.cli.roll_dice', side_effect=[(15, "Rolling 1d20: (15) = 15"), (12, "Rolling 1d20: (12) = 12")]):
        skip_dm, result = handler.handle("/attack Dagger")
    assert skip_dm is False
    assert result == "I attack with my Dagger against Goblin."
    out = capsys.readouterr().out
    assert "Hostile enemies detected. Starting encounter." in out
    dm.update_world_state.assert_any_call("pending_encounter_enemies", [])


# ---------------------------------------------------------------------------
# /sheet
# ---------------------------------------------------------------------------

def test_sheet_skips_dm(handler, player_sheet):
    skip_dm, result = handler.handle("/sheet")
    assert skip_dm is True
    player_sheet.refresh_cache.assert_called_once()


# ---------------------------------------------------------------------------
# /cast
# ---------------------------------------------------------------------------

def test_cast_success_reaches_dm(handler, player_sheet):
    player_sheet.cast_spell.return_value = True
    skip_dm, result = handler.handle("/cast Magic Missile")
    assert skip_dm is False
    assert result == "I cast the Magic Missile spell."
    player_sheet.cast_spell.assert_called_once_with(1, 'Magic Missile')


def test_cast_with_target_reaches_dm(handler, player_sheet):
    player_sheet.cast_spell.return_value = True
    skip_dm, result = handler.handle("/cast Fire Bolt at the whispering")
    assert skip_dm is False
    assert result == "I cast the Fire Bolt spell at the whispering."
    player_sheet.cast_spell.assert_called_once_with(0, 'Fire Bolt')


def test_cast_prints_spell_math(handler, player_sheet, capsys):
    player_sheet.cast_spell.return_value = True
    skip_dm, _ = handler.handle("/cast Magic Missile")
    assert skip_dm is False
    out = capsys.readouterr().out
    assert "Casting Magic Missile:" in out
    assert "Spell Attack: 1d20 + INT mod (+3) + proficiency (+2) = +5" in out
    assert "Save DC: 8 + proficiency (2) + INT mod (+3) = 13" in out
    assert "Slot Use: Level 1 slot (2/2 available before casting)" in out


def test_cast_rejected_when_not_player_turn(player_sheet, dm, capsys):
    npc = MagicMock()
    npc.name = "Bram"
    npc_sheet = MagicMock()
    npc_sheet.initiative = 1
    h = CommandHandler(player_sheet, {"wizard": player_sheet, "bram": npc_sheet}, npcs={"bram": npc}, dm=dm)
    h.advance_turn()
    player_sheet.cast_spell.return_value = True
    skip_dm, result = h.handle("/cast Magic Missile")
    assert skip_dm is True
    assert result == ""
    assert "It is currently Bram's turn, not yours." in capsys.readouterr().out


def test_cast_auto_starts_pending_encounter_for_offensive_spell(handler, player_sheet, dm, capsys):
    dm.world_state["pending_encounter_enemies"] = ["Goblin"]
    player_sheet.cast_spell.return_value = True
    with patch('dnd.cli.roll_dice', side_effect=[(15, "Rolling 1d20: (15) = 15"), (12, "Rolling 1d20: (12) = 12")]):
        skip_dm, result = handler.handle("/cast Magic Missile")
    assert skip_dm is False
    assert result == "I cast the Magic Missile spell."
    out = capsys.readouterr().out
    assert "Hostile enemies detected. Starting encounter." in out
    dm.update_world_state.assert_any_call("pending_encounter_enemies", [])


def test_cast_non_offensive_spell_does_not_auto_start_encounter(handler, player_sheet, dm, capsys):
    dm.world_state["pending_encounter_enemies"] = ["Goblin"]
    player_sheet.spells = [{'name': 'Light', 'level': 0}]
    player_sheet.cast_spell.return_value = True
    player_sheet.get_spellcasting_breakdown.return_value = {
        "spell_name": "Light",
        "level": 0,
        "ability_name": "INT",
        "ability_mod": 3,
        "proficiency_bonus": 2,
        "spell_save_dc": 13,
        "spell_attack_bonus": 5,
        "range": "Touch",
        "casting_time": "1 action",
        "duration": "1 hour",
        "slots_current": None,
        "slots_max": None,
    }
    skip_dm, result = handler.handle("/cast Light")
    assert skip_dm is False
    assert result == "I cast the Light spell."
    assert "Hostile enemies detected. Starting encounter." not in capsys.readouterr().out


def test_cast_no_slots_skips_dm(handler, player_sheet):
    player_sheet.cast_spell.return_value = False
    skip_dm, result = handler.handle("/cast Magic Missile")
    assert skip_dm is True


def test_cast_unknown_spell_skips_dm(handler):
    skip_dm, result = handler.handle("/cast Fireball")
    assert skip_dm is True


def test_cast_no_args_skips_dm(handler):
    skip_dm, result = handler.handle("/cast")
    assert skip_dm is True


# ---------------------------------------------------------------------------
# /shortrest / /longrest
# ---------------------------------------------------------------------------

def test_shortrest_success_reaches_dm(handler, player_sheet):
    skip_dm, result = handler.handle("/shortrest 2")
    assert skip_dm is False
    assert "short rest" in result
    assert "2" in result
    player_sheet.take_short_rest.assert_called_once_with(2)


def test_shortrest_no_args_skips_dm(handler):
    skip_dm, result = handler.handle("/shortrest")
    assert skip_dm is True


def test_shortrest_invalid_args_skips_dm(handler):
    skip_dm, result = handler.handle("/shortrest abc")
    assert skip_dm is True


def test_longrest_reaches_dm(handler, player_sheet):
    skip_dm, result = handler.handle("/longrest")
    assert skip_dm is False
    assert result == "I take a long rest."
    player_sheet.take_long_rest.assert_called_once()


# ---------------------------------------------------------------------------
# /equip / /unequip
# ---------------------------------------------------------------------------

def test_equip_success_reaches_dm(handler, player_sheet):
    player_sheet.inventory_items = [('Dagger', 1)]
    skip_dm, result = handler.handle("/equip Dagger")
    assert skip_dm is False
    assert result == "I equip the Dagger."
    player_sheet.equip_item.assert_called_once_with("Dagger")


def test_equip_item_not_in_inventory_skips_dm(handler, player_sheet):
    player_sheet.inventory_items = []
    skip_dm, result = handler.handle("/equip Sword")
    assert skip_dm is True


def test_equip_no_args_skips_dm(handler):
    skip_dm, result = handler.handle("/equip")
    assert skip_dm is True


def test_unequip_success_reaches_dm(handler, player_sheet):
    player_sheet.inventory_items = [('Dagger', 1)]
    skip_dm, result = handler.handle("/unequip Dagger")
    assert skip_dm is False
    assert result == "I unequip the Dagger."
    player_sheet.unequip_item.assert_called_once_with("Dagger")


def test_unequip_item_not_in_inventory_skips_dm(handler, player_sheet):
    player_sheet.inventory_items = []
    skip_dm, result = handler.handle("/unequip Sword")
    assert skip_dm is True


# ---------------------------------------------------------------------------
# /inventory
# ---------------------------------------------------------------------------

def test_inventory_skips_dm(handler, player_sheet, capsys):
    player_sheet.inventory_items = [('Dagger', 1)]
    player_sheet.equipped_items = []
    player_sheet.unequipped_items = ['Dagger']
    skip_dm, result = handler.handle("/inventory")
    assert skip_dm is True
    out = capsys.readouterr().out
    assert "Inventory" in out
    assert "Gold: 100 gp" in out
    assert "Pack:" in out


# ---------------------------------------------------------------------------
# /rage / /unrage
# ---------------------------------------------------------------------------

def test_rage_barbarian_skips_dm(handler, player_sheet):
    player_sheet.class_name = "Barbarian"
    skip_dm, result = handler.handle("/rage")
    assert skip_dm is True
    player_sheet.start_rage.assert_called_once()


def test_rage_non_barbarian_skips_dm(handler, player_sheet):
    player_sheet.class_name = "Wizard"
    skip_dm, result = handler.handle("/rage")
    assert skip_dm is True
    player_sheet.start_rage.assert_not_called()


def test_unrage_barbarian_skips_dm(handler, player_sheet):
    player_sheet.class_name = "Barbarian"
    skip_dm, result = handler.handle("/unrage")
    assert skip_dm is True
    player_sheet.end_rage.assert_called_once()


# ---------------------------------------------------------------------------
# /addcondition / /removecondition
# ---------------------------------------------------------------------------

def test_addcondition_no_duration(handler):
    char_sheet = MagicMock()
    handler.character_sheets = {'wizard': char_sheet}
    skip_dm, result = handler.handle("/addcondition wizard Poisoned")
    assert skip_dm is True
    char_sheet.add_condition.assert_called_once_with("Poisoned", -1)


def test_addcondition_with_duration(handler):
    char_sheet = MagicMock()
    handler.character_sheets = {'wizard': char_sheet}
    skip_dm, result = handler.handle("/addcondition wizard Poisoned 3")
    assert skip_dm is True
    char_sheet.add_condition.assert_called_once_with("Poisoned", 3)


def test_addcondition_unknown_character(handler, capsys):
    skip_dm, result = handler.handle("/addcondition nobody Poisoned")
    assert skip_dm is True
    assert "not found" in capsys.readouterr().out


def test_addcondition_bad_args_skips_dm(handler):
    skip_dm, result = handler.handle("/addcondition")
    assert skip_dm is True


def test_removecondition(handler):
    char_sheet = MagicMock()
    handler.character_sheets = {'wizard': char_sheet}
    skip_dm, result = handler.handle("/removecondition wizard Poisoned")
    assert skip_dm is True
    char_sheet.remove_condition.assert_called_once_with("Poisoned")


def test_removecondition_bad_args_skips_dm(handler):
    skip_dm, result = handler.handle("/removecondition")
    assert skip_dm is True


# ---------------------------------------------------------------------------
# /worldstate
# ---------------------------------------------------------------------------

def test_worldstate_no_args_prints_state(handler, dm, capsys):
    skip_dm, result = handler.handle("/worldstate")
    assert skip_dm is True
    assert "tavern" in capsys.readouterr().out


def test_worldstate_set_key(handler, dm):
    skip_dm, result = handler.handle("/worldstate location dungeon")
    assert skip_dm is True
    dm.update_world_state.assert_called_once_with("location", "dungeon")


# ---------------------------------------------------------------------------
# /teach and suggested actions
# ---------------------------------------------------------------------------

def test_teach_toggle(handler, capsys):
    skip_dm, result = handler.handle("/teach")
    assert skip_dm is True
    assert result == ""
    assert "Teaching mode is on." in capsys.readouterr().out


def test_suggested_actions_include_beginner_prompts(handler):
    suggestions = handler.get_suggested_actions()
    assert "/attack Dagger" in suggestions
    assert "/cast Fire Bolt" in suggestions
    assert "/sheet" in suggestions
    assert len(suggestions) == 4


def test_suggested_actions_include_slash_ask_when_companion_exists(player_sheet, dm):
    npc = MagicMock()
    npc.name = "Aria"
    h = CommandHandler(player_sheet, {"wizard": player_sheet}, npcs={"aria": npc}, dm=dm)
    suggestions = h.get_suggested_actions()
    assert "/ask aria What do you notice?" in suggestions


def test_turn_status_defaults_to_player(handler, capsys):
    skip_dm, _ = handler.handle("/turn")
    assert skip_dm is True
    out = capsys.readouterr().out
    assert "Round: 1" in out
    assert "Active Turn: Wizard" in out


def test_turn_advances_to_next_actor(player_sheet, dm):
    npc = MagicMock()
    npc.name = "Aria"
    npc_sheet = MagicMock()
    npc_sheet.initiative = 1
    h = CommandHandler(player_sheet, {'wizard': player_sheet, 'aria': npc_sheet}, npcs={'aria': npc}, dm=dm)
    assert h.current_actor_name == "Wizard"
    h.advance_turn()
    assert h.current_actor_name == "Aria"
    h.advance_turn()
    assert h.current_actor_name == "Wizard"
    assert h.round_number == 2


def test_npc_turn_command_runs_active_companion(player_sheet, dm, capsys):
    npc = MagicMock()
    npc.name = "Aria"
    npc.generate_turn_action.return_value = "I check the doorway for trouble."
    npc_sheet = MagicMock()
    npc_sheet.initiative = 1
    h = CommandHandler(player_sheet, {'wizard': player_sheet, 'aria': npc_sheet}, npcs={'aria': npc}, dm=dm)
    dm.world_state["recent_party_actions"] = ["Wizard acted: I move to the doorway."]
    h.advance_turn()
    skip_dm, _ = h.handle("/npcturn")
    assert skip_dm is True
    npc.generate_turn_action.assert_called_once_with(
        dm.history,
        dm.world_state["scene_summary"] if "scene_summary" in dm.world_state else "No scene summary recorded yet.",
        ["Wizard acted: I move to the doorway."],
    )
    out = capsys.readouterr().out
    assert "Aria:" in out
    assert "I check the doorway for trouble." in out
    assert "Active Turn: Wizard" in out
    dm.add_history.assert_called_once_with("assistant", "Aria: I check the doorway for trouble.")
    dm.update_world_state.assert_any_call("recent_party_actions", ["Wizard acted: I move to the doorway.", "Aria acted: I check the doorway for trouble."])


def test_npc_turn_suggestions_when_companion_active(player_sheet, dm):
    npc = MagicMock()
    npc.name = "Aria"
    npc_sheet = MagicMock()
    npc_sheet.initiative = 1
    h = CommandHandler(player_sheet, {'wizard': player_sheet, 'aria': npc_sheet}, npcs={'aria': npc}, dm=dm)
    h.advance_turn()
    suggestions = h.get_suggested_actions()
    assert suggestions == ["/npcturn", "/endturn", "/ask aria What do you want to do?", "/turn"]


def test_encounter_start_builds_initiative_order(player_sheet, dm, capsys):
    h = CommandHandler(player_sheet, {'wizard': player_sheet}, npcs={}, dm=dm)
    with patch('dnd.cli.roll_dice', side_effect=[(15, "Rolling 1d20: (15) = 15"), (12, "Rolling 1d20: (12) = 12")]):
        skip_dm, _ = h.handle("/encounter start Goblin:1")
    assert skip_dm is True
    assert h.encounter is not None
    out = capsys.readouterr().out
    assert "Encounter started against: Goblin." in out
    assert "Active Turn: Wizard" in out
    assert "[enemy]" in out


def test_encounter_workflow_prompts_for_enemies(player_sheet, dm, capsys):
    h = CommandHandler(player_sheet, {'wizard': player_sheet}, npcs={}, dm=dm)
    with patch("builtins.input", side_effect=["Goblin", "1", "Wolf", "", "", ""]), patch(
        'dnd.cli.roll_dice',
        side_effect=[(15, "Rolling 1d20: (15) = 15"), (12, "Rolling 1d20: (12) = 12"), (9, "Rolling 1d20: (9) = 9")],
    ):
        skip_dm, _ = h.handle("/encounter")
    assert skip_dm is True
    assert h.encounter is not None
    out = capsys.readouterr().out
    assert "Encounter setup" in out
    assert "Encounter started against: Goblin, Wolf." in out


def test_encounter_uses_pending_detected_enemies(player_sheet, dm, capsys):
    h = CommandHandler(player_sheet, {'wizard': player_sheet}, npcs={}, dm=dm)
    dm.world_state["pending_encounter_enemies"] = ["Goblin", "Goblin", "Wolf"]
    with patch("builtins.input", return_value=""), patch(
        'dnd.cli.roll_dice',
        side_effect=[
            (15, "Rolling 1d20: (15) = 15"),
            (12, "Rolling 1d20: (12) = 12"),
            (11, "Rolling 1d20: (11) = 11"),
            (10, "Rolling 1d20: (10) = 10"),
        ],
    ):
        skip_dm, _ = h.handle("/encounter")
    assert skip_dm is True
    out = capsys.readouterr().out
    assert "Encounter started against: Goblin, Goblin, Wolf." in out
    dm.update_world_state.assert_any_call("pending_encounter_enemies", [])


def test_enemy_turn_forwards_to_dm(player_sheet, dm, capsys):
    h = CommandHandler(player_sheet, {'wizard': player_sheet}, npcs={}, dm=dm)
    h.encounter = {
        "order": [
            {"name": "Goblin", "type": "enemy", "modifier": 1, "roll": 14, "total": 15},
            {"name": "Wizard", "type": "player", "modifier": 2, "roll": 10, "total": 12},
        ],
        "index": 0,
        "round": 1,
    }
    skip_dm, prompt = h.handle("/enemyturn")
    assert skip_dm is False
    assert "Goblin" in prompt
    assert "Enemy turn: Goblin" in capsys.readouterr().out


def test_encounter_suggestions_for_enemy_turn(player_sheet, dm):
    h = CommandHandler(player_sheet, {'wizard': player_sheet}, npcs={}, dm=dm)
    h.encounter = {
        "order": [
            {"name": "Goblin", "type": "enemy", "modifier": 1, "roll": 14, "total": 15},
            {"name": "Wizard", "type": "player", "modifier": 2, "roll": 10, "total": 12},
        ],
        "index": 0,
        "round": 1,
    }
    assert h.get_suggested_actions() == ["/enemyturn", "/turn", "/rules attacks", "/sheet"]


def test_encounter_end_clears_state(player_sheet, dm, capsys):
    h = CommandHandler(player_sheet, {'wizard': player_sheet}, npcs={}, dm=dm)
    h.encounter = {
        "order": [{"name": "Goblin", "type": "enemy", "modifier": 1, "roll": 14, "total": 15}],
        "index": 0,
        "round": 1,
    }
    skip_dm, _ = h.handle("/encounter end")
    assert skip_dm is True
    assert h.encounter is None
    dm.update_world_state.assert_called_with("encounter_enemies", "")
    assert "Encounter ended." in capsys.readouterr().out


def test_help_lists_topics(handler, capsys):
    skip_dm, result = handler.handle("/help")
    assert skip_dm is True
    assert result == ""
    out = capsys.readouterr().out
    assert "Topics: commands, combat, spells, exploration" in out


def test_help_topic_prints_entries(handler, capsys):
    skip_dm, _ = handler.handle("/help combat")
    assert skip_dm is True
    out = capsys.readouterr().out
    assert "Help: Combat" in out
    assert "/attack <weapon>" in out


def test_rules_topic_prints_reference(handler, capsys):
    skip_dm, _ = handler.handle("/rules advantage")
    assert skip_dm is True
    out = capsys.readouterr().out
    assert "Rules: Advantage" in out
    assert "rolling two d20s" in out


def test_journal_prints_world_state_summary(handler, capsys):
    skip_dm, _ = handler.handle("/journal")
    assert skip_dm is True
    out = capsys.readouterr().out
    assert "Current Location: tavern" in out
    assert "Find the missing caravan" in out
    assert "Investigate the old road" in out


def test_map_prints_known_locations(handler, capsys):
    skip_dm, _ = handler.handle("/map")
    assert skip_dm is True
    out = capsys.readouterr().out
    assert "Region: Greenfields" in out
    assert "Town square" in out
    assert "north to the old road" in out


# ---------------------------------------------------------------------------
# /shop / /buy
# ---------------------------------------------------------------------------

def test_shop_skips_dm(handler, capsys):
    skip_dm, result = handler.handle("/shop")
    assert skip_dm is True
    assert "Shop" in capsys.readouterr().out


def test_buy_skips_dm(handler, player_sheet):
    player_sheet.spend_gold.return_value = False  # can't afford
    skip_dm, result = handler.handle("/buy Healing Potion")
    assert skip_dm is True


# ---------------------------------------------------------------------------
# Unknown command
# ---------------------------------------------------------------------------

def test_unknown_command_skips_dm(handler, capsys):
    skip_dm, result = handler.handle("/unknowncmd")
    assert skip_dm is True
    assert "Unknown command" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# ask <npc>
# ---------------------------------------------------------------------------

def test_ask_valid_npc(player_sheet, dm, capsys):
    mock_npc = MagicMock()
    mock_npc.name = "Aria"
    mock_npc.generate_response.return_value = "We should check the north trail."
    h = CommandHandler(player_sheet, {}, npcs={'aria': mock_npc}, dm=dm)
    skip_dm, result = h.handle("ask aria What do you think?")
    assert skip_dm is True
    mock_npc.generate_response.assert_called_once_with("What do you think?", dm.history)
    dm.add_history.assert_called_once_with("assistant", "Aria: We should check the north trail.")
    out = capsys.readouterr().out
    assert "Conversation does not end your turn." in out
    assert "Active Turn:" in out


def test_slash_ask_valid_npc(player_sheet, dm, capsys):
    mock_npc = MagicMock()
    mock_npc.name = "Aria"
    mock_npc.generate_response.return_value = "The north trail looks safer."
    h = CommandHandler(player_sheet, {}, npcs={'aria': mock_npc}, dm=dm)
    skip_dm, result = h.handle("/ask aria What do you think?")
    assert skip_dm is True
    assert result == ""
    mock_npc.generate_response.assert_called_once_with("What do you think?", dm.history)
    dm.add_history.assert_called_once_with("assistant", "Aria: The north trail looks safer.")
    out = capsys.readouterr().out
    assert "Conversation does not end your turn." in out
    assert "Suggested actions:" in out


def test_ask_unknown_npc_skips_dm(handler, capsys):
    skip_dm, result = handler.handle("ask nobody Hello")
    assert skip_dm is True
    assert "don't have a companion" in capsys.readouterr().out


def test_ask_missing_message_skips_dm(handler, capsys):
    skip_dm, result = handler.handle("ask aria")
    assert skip_dm is True
    assert "ask <name>" in capsys.readouterr().out


def test_slash_ask_workflow_prompts_for_companion_and_question(player_sheet, dm, capsys):
    mock_npc = MagicMock()
    mock_npc.name = "Aria"
    mock_npc.generate_response.return_value = "We should scout ahead."
    h = CommandHandler(player_sheet, {}, npcs={'aria': mock_npc}, dm=dm)
    with patch("builtins.input", side_effect=["Aria", "What do you see?"]):
        skip_dm, result = h.handle("/ask")
    assert skip_dm is True
    assert result == ""
    out = capsys.readouterr().out
    assert "Conversation setup" in out
    mock_npc.generate_response.assert_called_once_with("What do you see?", dm.history)
    assert "Conversation does not end your turn." in out


# ---------------------------------------------------------------------------
# Autocomplete
# ---------------------------------------------------------------------------

def test_command_completion_matches_prefix(handler):
    assert "/cast" in handler.get_completion_candidates("/ca")


def test_cast_completion_suggests_known_spells(handler):
    completions = handler.get_completion_candidates("/cast M")
    assert completions == ["/cast Magic Missile"]


def test_help_completion_suggests_topics(handler):
    completions = handler.get_completion_candidates("/help c")
    assert "/help combat" in completions
    assert "/help commands" in completions


def test_ask_completion_suggests_companion_names(player_sheet, dm):
    npc = MagicMock()
    npc.name = "Aria"
    h = CommandHandler(player_sheet, {"wizard": player_sheet}, npcs={"aria": npc}, dm=dm)
    assert h.get_completion_candidates("ask a") == ["ask aria "]


def test_slash_ask_completion_suggests_companion_names(player_sheet, dm):
    npc = MagicMock()
    npc.name = "Aria"
    h = CommandHandler(player_sheet, {"wizard": player_sheet}, npcs={"aria": npc}, dm=dm)
    assert h.get_completion_candidates("/ask a") == ["/ask aria "]


def test_worldstate_completion_uses_known_keys(handler):
    completions = handler.get_completion_candidates("/worldstate ob")
    assert completions == ["/worldstate objective"]


def test_encounter_completion_suggests_enemy_names(handler):
    completions = handler.get_completion_candidates("/encounter start Go")
    assert "/encounter start Goblin" in completions
    assert "/encounter start Goblin:1" in completions


def test_encounter_completion_handles_additional_enemy_entries(handler):
    completions = handler.get_completion_candidates("/encounter start Goblin, Or")
    assert "/encounter start Goblin, Orc" in completions
    assert "/encounter start Goblin, Orc:1" in completions
