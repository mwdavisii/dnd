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
    sheet.class_name = "Wizard"
    sheet.spells = [
        {'name': 'Fire Bolt', 'level': 0},
        {'name': 'Magic Missile', 'level': 1},
    ]
    sheet.inventory_items = [('Dagger', 1), ('Spellbook', 1)]
    sheet.equipped_items = []
    sheet.unequipped_items = ['Dagger', 'Spellbook']
    sheet._id = 1
    return sheet


@pytest.fixture
def dm():
    mock_dm = MagicMock()
    mock_dm.history = []
    mock_dm.world_state = {'location': 'tavern'}
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
    assert "Inventory" in capsys.readouterr().out


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

def test_ask_valid_npc(player_sheet, dm):
    mock_npc = MagicMock()
    mock_npc.name = "Aria"
    h = CommandHandler(player_sheet, {}, npcs={'aria': mock_npc}, dm=dm)
    skip_dm, result = h.handle("ask aria What do you think?")
    assert skip_dm is True
    mock_npc.generate_response.assert_called_once_with("What do you think?", dm.history)


def test_ask_unknown_npc_skips_dm(handler, capsys):
    skip_dm, result = handler.handle("ask nobody Hello")
    assert skip_dm is True
    assert "don't have a companion" in capsys.readouterr().out


def test_ask_missing_message_skips_dm(handler, capsys):
    skip_dm, result = handler.handle("ask aria")
    assert skip_dm is True
    assert "ask <name>" in capsys.readouterr().out
