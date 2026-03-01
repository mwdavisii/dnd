# tests/test_character.py
import pytest
import os
from dnd.database import initialize_database, get_db_connection, seed_spells, DB_FILE
from dnd.character import CharacterSheet
from dnd.character_creator import run_character_creation

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

    # Create a known character for testing
    # Use a sequential mock since the character creator uses bare "> " prompts
    inputs = iter(["Testus", "12", "3", "1", "INT", "CON", ""])
    monkeypatch.setattr('builtins.input', lambda prompt: next(inputs))
    monkeypatch.setattr('dnd.character_creator.clear_screen', lambda: None)
    
    player_name = run_character_creation()

    yield player_name # This provides the player_name to the test function

    # Teardown (not strictly necessary with tmp_path, but good practice)
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

def test_wizard_stat_calculation(setup_test_db):
    """Tests if stats are calculated correctly for our test Wizard."""
    sheet = CharacterSheet(name="Testus")
    
    # Base Wizard array: INT 15, CON 13
    # Background bonus: +2 INT, +1 CON
    # Final stats should be: INT 17, CON 14
    assert sheet.stats["INT"] == 17
    assert sheet.stats["CON"] == 14
    
    # Check modifiers
    assert sheet.ability_modifiers["INT"] == +3
    assert sheet.ability_modifiers["CON"] == +2

def test_wizard_hp_and_ac(setup_test_db):
    """Tests HP and AC calculation."""
    sheet = CharacterSheet(name="Testus")

    # Wizard base HP is 6. CON modifier is +2. So, 8 HP.
    assert sheet.max_hp == 8
    assert sheet.current_hp == 8

    # Unarmored AC = 10 + DEX mod. DEX is 12, so mod is +1. AC should be 11.
    assert sheet.armor_class == 11

def test_wizard_spellcasting_stats(setup_test_db):
    """Tests spell save DC and attack bonus."""
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
    assert "Cure Wounds" not in spell_names
