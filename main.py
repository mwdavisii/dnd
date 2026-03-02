import re
import os
import json
from dnd.dm.agent import DungeonMaster
from dnd.dm.prompts import ADVENTURE_START_PROMPT
from dnd.npc.agent import NPCAgent
from dnd.npc.prompts import NPC_ARCHETYPES
from dnd.game import roll_dice
from dnd.character import CharacterSheet
from dnd.database import initialize_database, get_db_connection, seed_npcs, seed_spells, DB_FILE
from dnd.character_creator import run_character_creation, clear_screen
from dnd.data import STORE_INVENTORY # Import STORE_INVENTORY
from dnd.cli import CommandHandler

def main():
    """Main function to run the D&D game."""
    
    player_name = "Player" # Default name

    # --- Game Setup ---
    if os.path.exists(DB_FILE):
        choice = ""
        while choice.lower() not in ['c', 'n']:
            choice = input("Saved game found. (C)ontinue or start a (N)ew Game? > ")
        
        if choice.lower() == 'n':
            os.remove(DB_FILE)
            clear_screen()
            print("Starting a new adventure...")
    
    if not os.path.exists(DB_FILE):
        initialize_database()
        seed_spells()
        player_name = run_character_creation()
        seed_npcs()

    # --- Dynamic Character Loading ---
    conn = get_db_connection()
    # Get player name if not already set from character creation
    if player_name == "Player":
        player_name = conn.execute("SELECT name FROM characters WHERE is_player = 1").fetchone()['name']

    npc_names = [row['name'] for row in conn.execute("SELECT name FROM characters WHERE is_player = 0").fetchall()]
    conn.close()

    player_sheet = CharacterSheet(name=player_name)
    archetype_map = {archetype['name']: archetype for archetype in NPC_ARCHETYPES}
    
    character_sheets = { player_name.lower(): player_sheet }
    npcs = {}
    companion_descriptions = []

    for name in npc_names:
        if name in archetype_map:
            archetype = archetype_map[name]
            character_sheets[name.lower()] = CharacterSheet(name=name)
            npcs[name.lower()] = NPCAgent(
                name=archetype['name'],
                class_name=archetype['class'],
                system_prompt=archetype['system_prompt']
            )
            companion_descriptions.append(f"{archetype['name']} the {archetype['class'].lower()}")
    
    dm = DungeonMaster()
    handler = CommandHandler(player_sheet, character_sheets, npcs, dm)

    # --- Game Start ---
    clear_screen()
    print("Welcome to your D&D adventure!")
    print(f"You are {player_name}.")
    print(f"Your stats:\n{player_sheet}")
    if companion_descriptions:
        print(f"Your companions are {', and '.join(companion_descriptions)}.")
    print("-" * 20)
    print(ADVENTURE_START_PROMPT)

    # --- Main Game Loop ---
    while True:
        try:
            user_input = input("\n> ")
            if user_input.lower() in ["quit", "exit"]:
                print("The adventure ends... for now.")
                break

            if user_input.lower().startswith("/") or user_input.lower().startswith("ask "):
                skip_dm, user_input = handler.handle(user_input)
                if skip_dm:
                    continue
                if not user_input:
                    continue

            print("\nDM: ", end='')
            response = dm.generate_response(user_input, player_sheet, npcs)

            # Check for level up
            if "<level_up />" in response:
                print("\n--- LEVEL UP! ---")
                for sheet in character_sheets.values():
                    sheet.level_up()
                print("-----------------")
            
            # Check for gold award
            gold_match = re.search(r'<award_gold amount="(\d+)"(?: reason="[^"]*")? />', response)
            if gold_match:
                amount = int(gold_match.group(1))
                player_sheet.add_gold(amount)
                # Remove tag from DM response for cleaner display
                response = re.sub(r'<award_gold amount="(\d+)"(?: reason="[^"]*")? />', '', response).strip()


        except (KeyboardInterrupt, EOFError):
            print("\nThe adventure ends... for now.")
            break

        update_condition_durations()

def update_condition_durations():
    """Updates the duration of conditions for all characters."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    characters = cursor.execute("SELECT id FROM characters").fetchall()
    
    for char_row in characters:
        character_id = char_row['id']
        conditions = cursor.execute("SELECT id, duration_turns FROM conditions WHERE character_id = ?", (character_id,)).fetchall()
        
        for cond_row in conditions:
            condition_id = cond_row['id']
            duration = cond_row['duration_turns']
            
            if duration > 0:
                new_duration = duration - 1
                if new_duration == 0:
                    cursor.execute("DELETE FROM conditions WHERE id = ?", (condition_id,))
                else:
                    cursor.execute("UPDATE conditions SET duration_turns = ? WHERE id = ?", (new_duration, condition_id))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
