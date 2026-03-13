# dnd/database.py
import sqlite3
import json
import random
import re
from datetime import datetime
from pathlib import Path
from .npc.prompts import NPC_ARCHETYPES
from .data import SPELL_DATA

DEFAULT_DB_FILE = "dnd_game.db"
SAVE_DIR = Path("saves")
DB_FILE = DEFAULT_DB_FILE

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def _table_exists(cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None

def _table_columns(cursor, table_name: str) -> set[str]:
    return {row["name"] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}

def set_db_file(path: str):
    global DB_FILE
    DB_FILE = path

def ensure_save_dir():
    SAVE_DIR.mkdir(exist_ok=True)

def list_save_files() -> list[Path]:
    ensure_save_dir()
    saves = sorted(SAVE_DIR.glob("*.db"))
    legacy = Path(DEFAULT_DB_FILE)
    if legacy.exists():
        saves.append(legacy)
    return saves


def list_player_templates(exclude_path: str | None = None) -> list[dict]:
    templates = []
    excluded = str(Path(exclude_path).resolve()) if exclude_path else None
    for save_path in list_save_files():
        resolved_path = str(save_path.resolve())
        if excluded and resolved_path == excluded:
            continue
        try:
            conn = sqlite3.connect(save_path)
            conn.row_factory = sqlite3.Row
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(characters)").fetchall()}
            if "characters" not in {
                row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }:
                conn.close()
                continue
            select_fields = ["name", "class_name", "stats"]
            if "sex" in columns:
                select_fields.append("sex")
            if "pronouns" in columns:
                select_fields.append("pronouns")
            row = conn.execute(
                f"SELECT {', '.join(select_fields)} FROM characters WHERE is_player = 1 LIMIT 1"
            ).fetchone()
            conn.close()
            if not row:
                continue
            templates.append(
                {
                    "source_path": str(save_path),
                    "name": row["name"],
                    "class_name": row["class_name"],
                    "stats": json.loads(row["stats"]),
                    "sex": row["sex"] if "sex" in row.keys() else None,
                    "pronouns": row["pronouns"] if "pronouns" in row.keys() else None,
                }
            )
        except sqlite3.Error:
            continue
    return templates

def slugify_save_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return cleaned or datetime.now().strftime("save_%Y%m%d_%H%M%S")

def create_save_path(name: str | None = None) -> str:
    ensure_save_dir()
    base_name = slugify_save_name(name) if name else datetime.now().strftime("save_%Y%m%d_%H%M%S")
    candidate = SAVE_DIR / f"{base_name}.db"
    suffix = 2
    while candidate.exists():
        candidate = SAVE_DIR / f"{base_name}_{suffix}.db"
        suffix += 1
    return str(candidate)

def delete_save_file(path: str):
    Path(path).unlink(missing_ok=True)

def format_save_label(path: Path) -> str:
    if path.name == DEFAULT_DB_FILE:
        return "legacy_save"
    return path.stem

def get_save_metadata(path: Path) -> dict[str, str]:
    fallback = {
        "created_at": _format_timestamp(datetime.fromtimestamp(path.stat().st_ctime)) if path.exists() else "Unknown",
        "last_accessed_at": _format_timestamp(datetime.fromtimestamp(path.stat().st_mtime)) if path.exists() else "Unknown",
    }
    if not path.exists():
        return fallback

    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT created_at, last_accessed_at FROM save_metadata WHERE id = 1"
        ).fetchone()
        conn.close()
        if not row:
            return fallback
        return {
            "created_at": _format_timestamp(row["created_at"]),
            "last_accessed_at": _format_timestamp(row["last_accessed_at"]),
        }
    except sqlite3.Error:
        return fallback

def touch_save_accessed_at():
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO save_metadata (id, created_at, last_accessed_at)
        VALUES (1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET last_accessed_at = CURRENT_TIMESTAMP
        """
    )
    conn.commit()
    conn.close()

def _format_timestamp(value) -> str:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError:
            return str(value)
    else:
        return str(value)
    return dt.strftime("%Y-%m-%d %I:%M %p")

def create_game_session() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO game_sessions DEFAULT VALUES")
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def get_latest_session_id() -> int | None:
    conn = get_db_connection()
    row = conn.execute("SELECT id FROM game_sessions ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row["id"] if row else None

def ensure_game_session() -> int:
    latest = get_latest_session_id()
    if latest is not None:
        return latest
    return create_game_session()

def save_world_state(session_id: int, key: str, value):
    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO world_state (session_id, key, value) VALUES (?, ?, ?)
        ON CONFLICT(session_id, key) DO UPDATE SET value = excluded.value
        """,
        (session_id, key, json.dumps(value)),
    )
    conn.commit()
    conn.close()

def load_world_state(session_id: int) -> dict:
    conn = get_db_connection()
    rows = conn.execute("SELECT key, value FROM world_state WHERE session_id = ?", (session_id,)).fetchall()
    conn.close()
    return {row["key"]: json.loads(row["value"]) for row in rows}

def save_npc_memory(session_id: int, character_name: str, memory: str):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO npc_memories (session_id, character_name, memory_text) VALUES (?, ?, ?)",
        (session_id, character_name, memory),
    )
    conn.commit()
    conn.close()

def load_npc_memories(session_id: int, character_name: str, limit: int = 12) -> list[str]:
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT memory_text
        FROM npc_memories
        WHERE session_id = ? AND character_name = ?
        ORDER BY id DESC LIMIT ?
        """,
        (session_id, character_name, limit),
    ).fetchall()
    conn.close()
    return [row["memory_text"] for row in reversed(rows)]

def seed_npcs(num_companions: int = 2):
    """Seeds the database with the requested number of random NPC companions."""
    conn = get_db_connection()
    cursor = conn.cursor()

    num_companions = max(0, min(num_companions, len(NPC_ARCHETYPES)))
    if num_companions == 0:
        print("Starting without companions.")
        conn.close()
        return

    selected_npcs = random.sample(NPC_ARCHETYPES, num_companions)
    companion_names = ", ".join(npc['name'] for npc in selected_npcs)
    print(f"Generating your companions: {companion_names}.")

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
    CREATE TABLE IF NOT EXISTS game_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS save_metadata (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_accessed_at TEXT DEFAULT CURRENT_TIMESTAMP
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        class_name TEXT,
        sex TEXT,
        pronouns TEXT,
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS world_state (
        session_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL
        ,PRIMARY KEY (session_id, key),
        FOREIGN KEY (session_id) REFERENCES game_sessions (id)
    );""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS npc_memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        character_name TEXT NOT NULL,
        memory_text TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES game_sessions (id)
    );""")

    _migrate_legacy_schema(cursor)
    cursor.execute(
        """
        INSERT INTO save_metadata (id, created_at, last_accessed_at)
        VALUES (1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO NOTHING
        """
    )
    conn.commit()
    conn.close()

def _migrate_legacy_schema(cursor):
    _ensure_character_columns(cursor)
    _ensure_inventory_columns(cursor)
    _migrate_world_state_table(cursor)
    _migrate_npc_memories_table(cursor)

def _ensure_character_columns(cursor):
    if not _table_exists(cursor, "characters"):
        return
    columns = _table_columns(cursor, "characters")
    additions = {
        "sex": "TEXT",
        "pronouns": "TEXT",
        "spell_slots_l2_current": "INTEGER DEFAULT 0",
        "spell_slots_l2_max": "INTEGER DEFAULT 0",
        "spell_slots_l3_current": "INTEGER DEFAULT 0",
        "spell_slots_l3_max": "INTEGER DEFAULT 0",
        "gold": "INTEGER DEFAULT 0",
        "is_concentrating": "INTEGER DEFAULT 0",
        "is_raging": "INTEGER DEFAULT 0",
        "is_player": "INTEGER DEFAULT 0",
    }
    for column_name, column_def in additions.items():
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE characters ADD COLUMN {column_name} {column_def}")

def _ensure_inventory_columns(cursor):
    if not _table_exists(cursor, "inventory"):
        return
    columns = _table_columns(cursor, "inventory")
    if "equipped" not in columns:
        cursor.execute("ALTER TABLE inventory ADD COLUMN equipped INTEGER DEFAULT 0")

def _migrate_world_state_table(cursor):
    if not _table_exists(cursor, "world_state"):
        return
    columns = _table_columns(cursor, "world_state")
    if "session_id" in columns:
        return

    session_id = _ensure_game_session_row(cursor)
    cursor.execute("ALTER TABLE world_state RENAME TO world_state_legacy")
    cursor.execute("""
    CREATE TABLE world_state (
        session_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY (session_id, key),
        FOREIGN KEY (session_id) REFERENCES game_sessions (id)
    )""")
    legacy_rows = cursor.execute("SELECT key, value FROM world_state_legacy").fetchall()
    for row in legacy_rows:
        cursor.execute(
            "INSERT INTO world_state (session_id, key, value) VALUES (?, ?, ?)",
            (session_id, row["key"], row["value"]),
        )
    cursor.execute("DROP TABLE world_state_legacy")

def _migrate_npc_memories_table(cursor):
    if not _table_exists(cursor, "npc_memories"):
        return
    columns = _table_columns(cursor, "npc_memories")
    if "session_id" in columns:
        return

    session_id = _ensure_game_session_row(cursor)
    cursor.execute("ALTER TABLE npc_memories RENAME TO npc_memories_legacy")
    cursor.execute("""
    CREATE TABLE npc_memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        character_name TEXT NOT NULL,
        memory_text TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES game_sessions (id)
    )""")
    legacy_rows = cursor.execute("SELECT character_name, memory_text FROM npc_memories_legacy").fetchall()
    for row in legacy_rows:
        cursor.execute(
            "INSERT INTO npc_memories (session_id, character_name, memory_text) VALUES (?, ?, ?)",
            (session_id, row["character_name"], row["memory_text"]),
        )
    cursor.execute("DROP TABLE npc_memories_legacy")

def _ensure_game_session_row(cursor) -> int:
    row = cursor.execute("SELECT id FROM game_sessions ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return row["id"]
    cursor.execute("INSERT INTO game_sessions DEFAULT VALUES")
    return cursor.lastrowid

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
