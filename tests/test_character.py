# tests/test_character.py
import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock
from dnd.database import (
    create_save_path,
    create_game_session,
    delete_save_file,
    format_save_label,
    get_save_metadata,
    get_db_connection,
    initialize_database,
    list_save_files,
    load_npc_memories,
    load_world_state,
    save_npc_memory,
    save_world_state,
    set_db_file,
    seed_npcs,
    seed_spells,
    touch_save_accessed_at,
)
from dnd.character import CharacterSheet
from dnd.character_creator import (
    choose_companion_count,
    choose_game_mode,
    choose_session_round_budget,
    choose_spectator_settings,
    run_character_creation,
)
from dnd.data import CLASS_DATA
from dnd.npc.prompts import NPC_ARCHETYPES

# --- Test Fixture ---

@pytest.fixture
def setup_test_db(monkeypatch, tmp_path):
    """
    Creates a temporary, isolated database for a single test function.
    """
    # Create a temporary db file
    db_path = tmp_path / "test_dnd.db"
    
    # Use monkeypatch to make our app use this temp db
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)

    # Setup the database with tables and spells
    initialize_database()
    seed_spells()

    # --- Character Creation for Testus (Wizard) ---
    # Use a sequential mock since the character creator uses bare "> " prompts
    # Wizard (12), Sage (3), +2/+1 (1), INT (+2), CON (+1)
    inputs = iter(["Testus", "", "", "12", "3", "1", "INT", "CON", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('dnd.character_creator.list_player_templates', lambda: [])
    
    player_name = run_character_creation()

    yield player_name # This provides the player_name to the test function

    # Teardown (not strictly necessary with tmp_path, but good practice)
    os.remove(db_path)

@pytest.fixture
def setup_fighter_db(monkeypatch, tmp_path):
    """
    Creates a temporary, isolated database for a single test function with a Fighter.
    """
    db_path = tmp_path / "test_dnd_fighter.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)

    initialize_database()
    seed_spells()

    # Fighter (2), Soldier (4), +2/+1 (1), STR (+2), CON (+1)
    inputs = iter(["FighterTest", "", "", "2", "4", "1", "STR", "CON", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('dnd.character_creator.list_player_templates', lambda: [])
    
    player_name = run_character_creation()

    yield player_name
    os.remove(db_path)

@pytest.fixture
def setup_rogue_db(monkeypatch, tmp_path):
    """
    Creates a temporary, isolated database for a single test function with a Rogue.
    """
    db_path = tmp_path / "test_dnd_rogue.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)

    initialize_database()
    seed_spells()

    # Rogue (4), Criminal (2), +2/+1 (1), DEX (+2), INT (+1)
    inputs = iter(["RogueTest", "", "", "4", "2", "1", "DEX", "INT", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('dnd.character_creator.list_player_templates', lambda: [])
    
    player_name = run_character_creation()

    yield player_name
    os.remove(db_path)

@pytest.fixture
def setup_barbarian_db(monkeypatch, tmp_path):
    """
    Creates a temporary, isolated database for a single test function with a Barbarian.
    """
    db_path = tmp_path / "test_dnd_barbarian.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)

    initialize_database()
    seed_spells()

    # Barbarian (1), Soldier (4), +2/+1 (1), STR (+2), CON (+1)
    inputs = iter(["BarbarianTest", "", "", "1", "4", "1", "STR", "CON", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('dnd.character_creator.list_player_templates', lambda: [])
    
    player_name = run_character_creation()

    yield player_name
    os.remove(db_path)


# --- Tests ---

def test_character_creation_and_loading(setup_test_db):
    """Tests if a character is created and can be loaded."""
    player_name = setup_test_db
    assert player_name == "Testus"
    
    sheet = CharacterSheet(name="Testus")
    assert sheet.name == "Testus"
    assert sheet.class_name == "Wizard"
    assert sheet.level == 1


def test_character_creation_stores_optional_identity_fields(monkeypatch, tmp_path):
    db_path = tmp_path / "identity_fields.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    seed_spells()

    inputs = iter(["Aster", "nonbinary", "they/them", "12", "3", "1", "INT", "WIS", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('dnd.character_creator.list_player_templates', lambda: [])

    player_name = run_character_creation()
    assert player_name == "Aster"

    sheet = CharacterSheet(name="Aster")
    assert sheet.sex == "nonbinary"
    assert sheet.pronouns == "they/them"
    assert "Sex: nonbinary" in sheet.get_prompt_summary()
    assert "Pronouns: they/them" in sheet.get_prompt_summary()


def test_character_creation_reprompts_with_message_for_duplicate_plus_one(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "duplicate_stat_choice.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    seed_spells()

    inputs = iter(["Retry", "", "", "10", "3", "1", "CON", "CON", "WIS", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('dnd.character_creator.list_player_templates', lambda: [])

    run_character_creation()

    out = capsys.readouterr().out
    assert "You already gave CON the +2 bonus. Choose a different ability." in out


def test_clone_character_from_template_creates_level_one_copy(monkeypatch, tmp_path):
    db_path = tmp_path / "clone_template.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    seed_spells()
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr(
        'dnd.character_creator.list_player_templates',
        lambda: [
            {
                "source_path": "/tmp/source.db",
                "name": "Mike",
                "class_name": "Bard",
                "stats": {"STR": 8, "DEX": 16, "CON": 12, "INT": 14, "WIS": 10, "CHA": 15},
                "sex": None,
                "pronouns": "he/him",
            }
        ],
    )
    inputs = iter(["2", "1", "", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))

    player_name = run_character_creation()

    assert player_name == "Mike"
    sheet = CharacterSheet(name="Mike")
    assert sheet.class_name == "Bard"
    assert sheet.level == 1
    assert sheet.stats["DEX"] == 16
    assert sheet.stats["INT"] == 14
    assert sheet.pronouns == "he/him"

def test_wizard_stat_calculation(setup_test_db):
    """Tests if stats are calculated correctly for our test Wizard."""
    sheet = CharacterSheet(name="Testus")
    
    # Base Wizard array: INT 15, CON 13
    # Background bonus: +2 INT, +1 CON
    # Final stats should be: STR 8, DEX 12, CON 14, INT 17, WIS 14, CHA 10
    assert sheet.stats["STR"] == 8
    assert sheet.stats["DEX"] == 12
    assert sheet.stats["CON"] == 14
    assert sheet.stats["INT"] == 17
    assert sheet.stats["WIS"] == 14
    assert sheet.stats["CHA"] == 10
    
    # Check modifiers
    assert sheet.ability_modifiers["STR"] == -1
    assert sheet.ability_modifiers["DEX"] == +1
    assert sheet.ability_modifiers["CON"] == +2
    assert sheet.ability_modifiers["INT"] == +3
    assert sheet.ability_modifiers["WIS"] == +2
    assert sheet.ability_modifiers["CHA"] == +0


def test_wizard_hp_and_ac(setup_test_db):
    """Tests HP and AC calculation for Wizard (no armor initially)."""
    sheet = CharacterSheet(name="Testus")

    # Wizard base HP is 6. CON modifier is +2. So, 8 HP.
    assert sheet.max_hp == 8
    assert sheet.current_hp == 8

    # Unarmored AC = 10 + DEX mod. DEX is 12, so mod is +1. AC should be 11.
    assert sheet.armor_class == 11

def test_wizard_spellcasting_stats(setup_test_db):
    """Tests spell save DC and attack bonus for Wizard."""
    sheet = CharacterSheet(name="Testus")

    # Spellcasting ability is INT, modifier is +3. Proficiency bonus is +2.
    # DC = 8 + prof + mod = 8 + 2 + 3 = 13
    # Attack = prof + mod = 2 + 3 = 5
    assert sheet.spellcasting_ability == "INT"
    assert sheet.spell_save_dc == 13
    assert sheet.spell_attack_bonus == 5

def test_known_spells(setup_test_db):
    """Tests if the character knows the correct starting spells."""
    sheet = CharacterSheet(name="Testus")
    spell_names = [s['name'] for s in sheet.spells]
    
    # Wizard starts with Fire Bolt, Mage Hand, and Magic Missile
    assert "Fire Bolt" in spell_names
    assert "Mage Hand" in spell_names
    assert "Magic Missile" in spell_names
    assert "Cure Wounds" not in spell_names # Cleric spell

def test_add_gold(setup_test_db):
    """Tests that gold is added correctly."""
    sheet = CharacterSheet(name="Testus")
    initial_gold = sheet.gold # Wizard starts with 100
    amount_to_add = 100
    
    sheet.add_gold(amount_to_add)
    
    sheet.refresh_cache()
    assert sheet.gold == initial_gold + amount_to_add

def test_spend_gold_success(setup_test_db):
    """Tests that gold is spent correctly when balance is sufficient."""
    sheet = CharacterSheet(name="Testus")
    # Ensure starting with enough gold for the test
    sheet.add_gold(200) # Give 200, so 300 total (100 base)
    sheet.refresh_cache()
    initial_gold = sheet.gold
    amount_to_spend = 50
    
    assert sheet.spend_gold(amount_to_spend) is True
    
    sheet.refresh_cache()
    assert sheet.gold == initial_gold - amount_to_spend

def test_spend_gold_failure(setup_test_db):
    """Tests that gold is not spent if balance is insufficient."""
    sheet = CharacterSheet(name="Testus")
    # Set gold to a low amount (e.g., 25) for this test, from default 100
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE characters SET gold = ? WHERE name = ?", (25, "Testus"))
    conn.commit()
    conn.close()
    
    sheet.refresh_cache()
    initial_gold = sheet.gold # Should be 25
    amount_to_spend = 50
    
    assert sheet.spend_gold(amount_to_spend) is False
    
    sheet.refresh_cache()
    assert sheet.gold == initial_gold # Gold should not have changed


# --- NEW TESTS FOR RESTS AND INVENTORY ---

def test_short_rest_healing(setup_fighter_db, monkeypatch):
    """Tests short rest mechanics: spending hit dice, healing HP."""
    sheet = CharacterSheet(name="FighterTest")
    # Fighter base HP is 10. CON modifier will be +2 (CON 15 or 16). So, 12 HP.
    # Max HP is 12, Current HP is 12. Hit dice is d10. Hit dice current/max is 1/1.
    
    # Damage the fighter to test healing
    sheet.update_hp(-5) # HP to 7
    sheet.refresh_cache()
    assert sheet.current_hp == 7

    # Mock roll_dice to return a predictable value for d10
    # Healing = roll (e.g., 6) + CON mod (+2) = 8
    monkeypatch.setattr('dnd.character.roll_dice', MagicMock(return_value=(6, "Mock roll")))

    # Take a short rest, spend 1 hit die
    sheet.take_short_rest(1)

    sheet.refresh_cache()
    # Initial HP 7 + Healing 8 = 15. Capped at Max HP 12.
    assert sheet.current_hp == sheet.max_hp
    assert sheet.hit_dice_current == 0 # 1 spent

def test_short_rest_no_hit_dice(setup_fighter_db):
    """Tests short rest when no hit dice are available."""
    sheet = CharacterSheet(name="FighterTest")
    # Spend all hit dice
    conn = get_db_connection()
    conn.execute("UPDATE characters SET hit_dice_current = ? WHERE name = ?", (0, "FighterTest"))
    conn.commit()
    conn.close()
    sheet.refresh_cache()
    assert sheet.hit_dice_current == 0

    initial_hp = sheet.current_hp
    sheet.take_short_rest(1) # Try to spend 1 hit die

    sheet.refresh_cache()
    assert sheet.current_hp == initial_hp # HP should not change
    assert sheet.hit_dice_current == 0 # Still 0


def test_choose_companion_count_accepts_zero(monkeypatch):
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    inputs = iter(["0"])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    assert choose_companion_count(5) == 0


def test_choose_session_round_budget_medium(monkeypatch):
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('builtins.input', lambda prompt: "2")
    assert choose_session_round_budget() == 20


def test_choose_session_round_budget_custom(monkeypatch):
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    inputs = iter(["4", "15"])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    assert choose_session_round_budget() == 15


def test_choose_game_mode_spectator(monkeypatch):
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    monkeypatch.setattr('builtins.input', lambda prompt: "2")
    assert choose_game_mode() is True


def test_choose_spectator_settings_with_values(monkeypatch):
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    inputs = iter(["1.5"])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    assert choose_spectator_settings() == 1.5


def test_choose_spectator_settings_defaults(monkeypatch):
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    inputs = iter([""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    assert choose_spectator_settings() == 0.0


def test_choose_companion_count_retries_until_valid(monkeypatch):
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    inputs = iter(["abc", "9", "3"])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    assert choose_companion_count(5) == 3


def test_seed_npcs_zero_companions(monkeypatch, tmp_path):
    db_path = tmp_path / "test_seed_zero.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    seed_npcs(0)

    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM characters WHERE is_player = 0").fetchone()[0]
    conn.close()
    assert count == 0


def test_seed_npcs_requested_count(monkeypatch, tmp_path):
    db_path = tmp_path / "test_seed_three.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    seed_npcs(3)

    conn = get_db_connection()
    rows = conn.execute("SELECT name FROM characters WHERE is_player = 0").fetchall()
    conn.close()
    assert len(rows) == 3
    assert len({row["name"] for row in rows}) == 3


def test_npc_pool_supports_five_companions():
    assert len(NPC_ARCHETYPES) >= 5


def test_world_state_is_session_scoped(monkeypatch, tmp_path):
    db_path = tmp_path / "test_world_state_sessions.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    session_one = create_game_session()
    session_two = create_game_session()

    save_world_state(session_one, "objective", "Find the relic")
    save_world_state(session_two, "objective", "Guard the caravan")

    assert load_world_state(session_one)["objective"] == "Find the relic"
    assert load_world_state(session_two)["objective"] == "Guard the caravan"


def test_npc_memory_is_session_scoped_in_database(monkeypatch, tmp_path):
    db_path = tmp_path / "test_npc_memory_sessions.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()
    session_one = create_game_session()
    session_two = create_game_session()

    save_npc_memory(session_one, "Aria", "Remember the ruins")
    save_npc_memory(session_two, "Aria", "Remember the harbor")

    conn = get_db_connection()
    session_one_rows = conn.execute(
        "SELECT memory_text FROM npc_memories WHERE session_id = ? AND character_name = ?",
        (session_one, "Aria"),
    ).fetchall()
    session_two_rows = conn.execute(
        "SELECT memory_text FROM npc_memories WHERE session_id = ? AND character_name = ?",
        (session_two, "Aria"),
    ).fetchall()
    conn.close()

    assert [row["memory_text"] for row in session_one_rows] == ["Remember the ruins"]
    assert [row["memory_text"] for row in session_two_rows] == ["Remember the harbor"]


def test_save_file_helpers(monkeypatch, tmp_path):
    monkeypatch.setattr('dnd.database.SAVE_DIR', tmp_path / "saves")
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setattr('dnd.database.DEFAULT_DB_FILE', str(legacy_path))
    set_db_file(str(legacy_path))

    first_save = create_save_path("My First Campaign")
    assert first_save.endswith("my_first_campaign.db")
    Path(first_save).touch()
    legacy_path.touch()

    saves = list_save_files()
    assert Path(first_save) in saves
    assert legacy_path in saves
    assert format_save_label(Path(first_save)) == "my_first_campaign"

    delete_save_file(first_save)
    assert not Path(first_save).exists()


def test_save_metadata_defaults_and_updates(monkeypatch, tmp_path):
    db_path = tmp_path / "save_metadata.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()

    initial_metadata = get_save_metadata(db_path)
    assert initial_metadata["created_at"] != "Unknown"
    assert initial_metadata["last_accessed_at"] != "Unknown"

    conn = get_db_connection()
    conn.execute(
        "UPDATE save_metadata SET created_at = ?, last_accessed_at = ? WHERE id = 1",
        ("2026-03-01 10:00:00", "2026-03-02 11:30:00"),
    )
    conn.commit()
    conn.close()

    updated_metadata = get_save_metadata(db_path)
    assert updated_metadata["created_at"] == "2026-03-01 10:00 AM"
    assert updated_metadata["last_accessed_at"] == "2026-03-02 11:30 AM"


def test_touch_save_accessed_at_updates_existing_metadata(monkeypatch, tmp_path):
    db_path = tmp_path / "touch_save_metadata.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)
    initialize_database()

    conn = get_db_connection()
    conn.execute(
        "UPDATE save_metadata SET created_at = ?, last_accessed_at = ? WHERE id = 1",
        ("2026-03-01 10:00:00", "2026-03-01 10:00:00"),
    )
    conn.commit()
    conn.close()

    touch_save_accessed_at()

    metadata = get_save_metadata(db_path)
    assert metadata["created_at"] == "2026-03-01 10:00 AM"
    assert metadata["last_accessed_at"] != "2026-03-01 10:00 AM"


def test_create_save_path_uses_timestamp_when_name_missing(monkeypatch, tmp_path):
    monkeypatch.setattr('dnd.database.SAVE_DIR', tmp_path / "saves")
    save_path = Path(create_save_path())
    assert save_path.suffix == ".db"
    assert save_path.stem.startswith("save_")


def test_initialize_database_migrates_legacy_world_state(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_world_state.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)

    conn = get_db_connection()
    conn.execute("CREATE TABLE world_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO world_state (key, value) VALUES (?, ?)", ("objective", '"Find the relic"'))
    conn.commit()
    conn.close()

    initialize_database()

    state = load_world_state(1)
    assert state["objective"] == "Find the relic"


def test_initialize_database_migrates_legacy_npc_memories(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_npc_memories.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)

    conn = get_db_connection()
    conn.execute("CREATE TABLE npc_memories (id INTEGER PRIMARY KEY AUTOINCREMENT, character_name TEXT NOT NULL, memory_text TEXT NOT NULL)")
    conn.execute("INSERT INTO npc_memories (character_name, memory_text) VALUES (?, ?)", ("Aria", "Old memory"))
    conn.commit()
    conn.close()

    initialize_database()

    assert load_npc_memories(1, "Aria") == ["Old memory"]


def test_initialize_database_adds_missing_columns(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy_columns.db"
    monkeypatch.setattr('dnd.database.DB_FILE', db_path)

    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            class_name TEXT,
            hp_current INTEGER,
            hp_max INTEGER,
            stats TEXT,
            level INTEGER DEFAULT 1,
            proficiency_bonus INTEGER DEFAULT 2,
            hit_die_type TEXT DEFAULT 'd8',
            hit_dice_max INTEGER DEFAULT 1,
            hit_dice_current INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER,
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

    initialize_database()

    conn = get_db_connection()
    character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(characters)").fetchall()}
    inventory_columns = {row["name"] for row in conn.execute("PRAGMA table_info(inventory)").fetchall()}
    conn.close()

    assert "is_player" in character_columns
    assert "is_raging" in character_columns
    assert "sex" in character_columns
    assert "pronouns" in character_columns
    assert "equipped" in inventory_columns

def test_long_rest_full_restore(setup_test_db):
    """Tests long rest fully restores HP, Hit Dice, and Spell Slots."""
    sheet = CharacterSheet(name="Testus") # Wizard
    # Damage HP, spend spell slots, spend hit dice
    sheet.update_hp(-5) # HP to 3
    sheet.cast_spell(1, "Magic Missile") # Spend 1st level slot
    sheet.cast_spell(1, "Magic Missile") # Spend another 1st level slot
    
    # Spend hit dice (need to add more than 1 if level > 1, but this is level 1)
    # Mock roll_dice for short rest if necessary, but take_short_rest will do
    conn = get_db_connection()
    conn.execute("UPDATE characters SET hit_dice_current = ? WHERE name = ?", (0, "Testus"))
    conn.commit()
    conn.close()
    sheet.refresh_cache()

    assert sheet.current_hp < sheet.max_hp
    assert sheet.hit_dice_current == 0
    assert sheet.spell_slots[1]['current'] == 0 # Wizard has 2 L1 slots, both spent

    sheet.take_long_rest()

    sheet.refresh_cache()
    assert sheet.current_hp == sheet.max_hp
    assert sheet.hit_dice_current == sheet.hit_dice_max # Should be 1 for L1 char
    assert sheet.spell_slots[1]['current'] == sheet.spell_slots[1]['max'] # Should be 2 for L1 Wizard

def test_equip_unequip_item(setup_fighter_db):
    """Tests equipping and unequipping items."""
    sheet = CharacterSheet(name="FighterTest")
    # Fighter starts with Longsword, Shield, Chain Mail
    
    # Ensure they are initially unequipped (default in DB)
    assert "Longsword" in sheet.unequipped_items
    assert "Shield" in sheet.unequipped_items
    assert "Chain Mail" in sheet.unequipped_items
    assert not sheet.equipped_items # Initially empty

    # Equip Longsword
    sheet.equip_item("Longsword")
    sheet.refresh_cache()
    assert "Longsword" in sheet.equipped_items
    assert "Longsword" not in sheet.unequipped_items

    # Equip Shield
    sheet.equip_item("Shield")
    sheet.refresh_cache()
    assert "Shield" in sheet.equipped_items
    assert "Shield" not in sheet.unequipped_items

    # Unequip Longsword
    sheet.unequip_item("Longsword")
    sheet.refresh_cache()
    assert "Longsword" not in sheet.equipped_items
    assert "Longsword" in sheet.unequipped_items
    assert "Shield" in sheet.equipped_items # Shield should remain equipped

def test_equip_unknown_item(setup_test_db):
    """Tests attempting to equip an item not in inventory."""
    sheet = CharacterSheet(name="Testus")
    initial_equipped = list(sheet.equipped_items)
    sheet.equip_item("NonExistentItem")
    sheet.refresh_cache()
    assert list(sheet.equipped_items) == initial_equipped # Should not change

def test_armor_class_with_equipped_armor(setup_fighter_db):
    """Tests AC calculation with equipped armor and shield."""
    sheet = CharacterSheet(name="FighterTest") # STR 17(+3), DEX 14(+2), CON 15(+2), INT 8(-1), WIS 12(+1), CHA 10(+0)
    
    # Fighter starts with Chain Mail, Shield
    # Unarmored AC = 10 + DEX mod (2) = 12
    assert sheet.armor_class == 12 # Initially unequipped

    # Equip Chain Mail (Heavy, AC 16, ignores DEX)
    sheet.equip_item("Chain Mail")
    sheet.refresh_cache()
    assert sheet.armor_class == 16 # AC should be 16 from Chain Mail

    # Equip Shield (+2 AC)
    sheet.equip_item("Shield")
    sheet.refresh_cache()
    assert sheet.armor_class == 18 # AC should be 16 (Chain Mail) + 2 (Shield)

    # Unequip Shield
    sheet.unequip_item("Shield")
    sheet.refresh_cache()
    assert sheet.armor_class == 16

    # Unequip Chain Mail
    sheet.unequip_item("Chain Mail")
    sheet.refresh_cache()
    assert sheet.armor_class == 12 # Back to unarmored AC

def test_use_healing_potion(setup_fighter_db, monkeypatch):
    """Tests using a healing potion."""
    sheet = CharacterSheet(name="FighterTest") # Fighter with 12 max HP
    
    # Add a healing potion to inventory
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO inventory (character_id, item_name, quantity) VALUES (?, ?, ?)", (sheet._id, "Healing Potion", 1))
    conn.commit()
    conn.close()
    sheet.refresh_cache()
    assert "Healing Potion" in [item for item, _ in sheet.inventory_items]
    
    # Damage character
    sheet.update_hp(-10) # HP to 2
    sheet.refresh_cache()
    assert sheet.current_hp == 2

    # Mock roll_dice for 2d4+2 healing (e.g., 2+2+4=8 total healing)
    monkeypatch.setattr('dnd.character.roll_dice', MagicMock(return_value=(8, "mock roll")))

    sheet.use_item("Healing Potion")
    sheet.refresh_cache()

    # Healing = 8. Current HP 2 + 8 = 10.
    assert sheet.current_hp == 10
    assert "Healing Potion" not in [item for item, _ in sheet.inventory_items] # Should be consumed

def test_use_non_existent_item(setup_test_db):
    """Tests trying to use an item not in inventory."""
    sheet = CharacterSheet(name="Testus")
    initial_hp = sheet.current_hp
    initial_inventory = list(sheet.inventory_items)
    
    sheet.use_item("NonExistentPotion")
    sheet.refresh_cache()
    
    assert sheet.current_hp == initial_hp
    assert list(sheet.inventory_items) == initial_inventory

def test_use_non_consumable_item(setup_fighter_db):
    """Tests trying to use a non-consumable item (e.g., Longsword)."""
    sheet = CharacterSheet(name="FighterTest")
    initial_hp = sheet.current_hp
    initial_inventory = list(sheet.inventory_items)
    
    # Fighter starts with Longsword
    assert "Longsword" in [item for item, _ in sheet.inventory_items]

    sheet.use_item("Longsword")
    sheet.refresh_cache()

    assert sheet.current_hp == initial_hp
    assert "Longsword" in [item for item, _ in sheet.inventory_items] # Should still be there

def test_character_conditions(setup_fighter_db):
    """Tests adding, removing and checking character conditions."""
    sheet = CharacterSheet(name="FighterTest")
    
    # Get initial attack and skill modifiers
    initial_attack_bonus = sheet.get_attack_bonus("Longsword")
    initial_skill_modifier = sheet.get_skill_modifier("Athletics")
    
    # Add poisoned condition
    sheet.add_condition("Poisoned")
    sheet.refresh_cache()
    
    # Check that the character has the condition
    assert sheet.has_condition("Poisoned")
    
    # Check that attack and skill modifiers are reduced
    assert sheet.get_attack_bonus("Longsword") == initial_attack_bonus - 5
    assert sheet.get_skill_modifier("Athletics") == initial_skill_modifier - 5
    
    # Remove the condition
    sheet.remove_condition("Poisoned")
    sheet.refresh_cache()
    
    # Check that the character no longer has the condition
    assert not sheet.has_condition("Poisoned")
    
    # Check that attack and skill modifiers are back to normal
    assert sheet.get_attack_bonus("Longsword") == initial_attack_bonus
    assert sheet.get_skill_modifier("Athletics") == initial_skill_modifier

def test_sneak_attack(setup_rogue_db):
    """Tests the Rogue's sneak attack feature."""
    sheet = CharacterSheet(name="RogueTest")
    
    # Test normal attack
    damage_roll = sheet.get_damage_roll("Shortsword")
    assert damage_roll.count("1d6") == 1
    
    # Test sneak attack
    damage_roll_sneak = sheet.get_damage_roll("Shortsword", is_sneak_attack=True)
    assert damage_roll_sneak.count("1d6") == 2

def test_player_is_player_flag(setup_test_db):
    """Player created via run_character_creation should have is_player=1."""
    conn = get_db_connection()
    row = conn.execute("SELECT is_player FROM characters WHERE name = 'Testus'").fetchone()
    conn.close()
    assert row['is_player'] == 1


def test_player_query_by_is_player(setup_test_db):
    """WHERE is_player = 1 should return the player character."""
    conn = get_db_connection()
    row = conn.execute("SELECT name FROM characters WHERE is_player = 1").fetchone()
    conn.close()
    assert row is not None
    assert row['name'] == 'Testus'


def test_no_npcs_without_seed(setup_test_db):
    """Without seeding NPCs, WHERE is_player = 0 should return nothing."""
    conn = get_db_connection()
    rows = conn.execute("SELECT name FROM characters WHERE is_player = 0").fetchall()
    conn.close()
    assert rows == []


def test_learn_spell_adds_spell_to_character(setup_test_db):
    from dnd.character import CharacterSheet
    sheet = CharacterSheet(name=setup_test_db)
    initial_spell_count = len(sheet.spells)

    sheet.learn_spell("Thunderwave")

    sheet.refresh_cache()
    spell_names = [s["name"] for s in sheet.spells]
    assert "Thunderwave" in spell_names
    assert len(sheet.spells) == initial_spell_count + 1


def test_learn_spell_does_not_add_duplicate(setup_test_db):
    from dnd.character import CharacterSheet
    sheet = CharacterSheet(name=setup_test_db)
    sheet.learn_spell("Thunderwave")
    sheet.refresh_cache()
    count_after_first = len(sheet.spells)

    sheet.learn_spell("Thunderwave")
    sheet.refresh_cache()
    assert len(sheet.spells) == count_after_first


def test_learn_spell_ignores_unknown_spell(setup_test_db):
    from dnd.character import CharacterSheet
    sheet = CharacterSheet(name=setup_test_db)
    count = len(sheet.spells)

    sheet.learn_spell("FluxCapacitor")  # not in spells table

    sheet.refresh_cache()
    assert len(sheet.spells) == count  # no change


def test_barbarian_rage(setup_barbarian_db):
    """Tests the Barbarian's rage feature."""
    sheet = CharacterSheet(name="BarbarianTest")
    
    # Test that the character is not raging
    assert not sheet.is_raging
    
    # Start raging
    sheet.start_rage()
    sheet.refresh_cache()
    
    # Test that the character is raging
    assert sheet.is_raging
    
    # Test that the character has advantage on Strength saves
    assert sheet.get_saving_throw_modifier("STR") > sheet.ability_modifiers["STR"] + sheet.proficiency_bonus
    
    # Test that the character has resistance to bludgeoning, piercing, and slashing damage
    sheet.update_hp(-10, "bludgeoning")
    assert sheet.current_hp == sheet.max_hp - 5
    
    # Test that the character gets a damage bonus
    damage_roll = sheet.get_damage_roll("Greataxe")
    assert "+5" in damage_roll # +3 STR mod + 2 rage damage
    
    # End raging
    sheet.end_rage()
    sheet.refresh_cache()
    
    # Test that the character is no longer raging
    assert not sheet.is_raging
