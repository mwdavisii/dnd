# dnd/database.py
import sqlite3
import json
import random
from .npc.prompts import NPC_ARCHETYPES
from .data import SPELL_DATA

DB_FILE = "dnd_game.db"

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def seed_npcs():
    """Seeds the database with two random NPC companions."""
    conn = get_db_connection()
    cursor = conn.cursor()

    selected_npcs = random.sample(NPC_ARCHETYPES, 2)
    print(f"Generating your companions: {selected_npcs[0]['name']} and {selected_npcs[1]['name']}.")

    for npc in selected_npcs:
        cursor.execute(
            "INSERT INTO characters (name, class_name, hp_current, hp_max, stats, level, proficiency_bonus, hit_die_type, hit_dice_max, hit_dice_current, gold) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (npc['name'], npc['class'], npc['hp'], npc['hp'], json.dumps(npc['stats']), 1, 2, npc.get('hit_die', 'd8'), 1, 1, 50)
        )
        npc_id = cursor.lastrowid
        for item in npc['inventory']:
            cursor.execute("INSERT INTO inventory (character_id, item_name, quantity) VALUES (?, ?, ?)",(npc_id, item, 1))
    conn.commit()
    conn.close()

def initialize_database():
    """Initializes the database with all tables needed for the game."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        class_name TEXT,
        hp_current INTEGER, hp_max INTEGER, stats TEXT, level INTEGER DEFAULT 1,
        proficiency_bonus INTEGER DEFAULT 2, hit_die_type TEXT DEFAULT 'd8',
        hit_dice_max INTEGER DEFAULT 1, hit_dice_current INTEGER DEFAULT 1,
        spell_slots_l1_current INTEGER DEFAULT 0, spell_slots_l1_max INTEGER DEFAULT 0,
        spell_slots_l2_current INTEGER DEFAULT 0, spell_slots_l2_max INTEGER DEFAULT 0,
        spell_slots_l3_current INTEGER DEFAULT 0, spell_slots_l3_max INTEGER DEFAULT 0,
        gold INTEGER DEFAULT 0,
        is_concentrating INTEGER DEFAULT 0,
        is_raging INTEGER DEFAULT 0,
        is_player INTEGER DEFAULT 0
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT, character_id INTEGER, item_name TEXT NOT NULL,
        quantity INTEGER DEFAULT 1, equipped INTEGER DEFAULT 0, FOREIGN KEY (character_id) REFERENCES characters (id)
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proficiencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, type TEXT NOT NULL
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS character_proficiencies (
        character_id INTEGER, proficiency_id INTEGER, PRIMARY KEY (character_id, proficiency_id),
        FOREIGN KEY (character_id) REFERENCES characters (id),
        FOREIGN KEY (proficiency_id) REFERENCES proficiencies (id)
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS spells (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, level INTEGER NOT NULL,
        school TEXT NOT NULL, casting_time TEXT, range TEXT, components TEXT,
        duration TEXT, description TEXT NOT NULL
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS character_spells (
        character_id INTEGER, spell_id INTEGER, PRIMARY KEY (character_id, spell_id),
        FOREIGN KEY (character_id) REFERENCES characters (id),
        FOREIGN KEY (spell_id) REFERENCES spells (id)
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conditions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        character_id INTEGER,
        condition_name TEXT NOT NULL,
        duration_turns INTEGER DEFAULT -1,
        FOREIGN KEY (character_id) REFERENCES characters (id)
    );""")
    
    conn.commit()
    conn.close()

def seed_spells():
    """Seeds the database with master spell data if the table is empty."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM spells")
    if cursor.fetchone()[0] > 0:
        return # Spells already seeded

    print("Seeding database with master spell list...")
    for spell_name, data in SPELL_DATA.items():
        cursor.execute(
            """INSERT INTO spells (name, level, school, casting_time, range, components, duration, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (spell_name, data['level'], data['school'], data['casting_time'], data['range'], data['components'], data['duration'], data['description'])
        )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    initialize_database()
    seed_spells()
    print("Database initialized and seeded.")
