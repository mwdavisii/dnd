import re
import os
import json
from pathlib import Path
from dnd.dm.agent import DungeonMaster
from dnd.npc.agent import NPCAgent
from dnd.npc.prompts import NPC_ARCHETYPES
from dnd.game import roll_dice
from dnd.character import CharacterSheet
from dnd.database import (
    DB_FILE,
    create_game_session,
    create_save_path,
    delete_save_file,
    ensure_game_session,
    format_save_label,
    get_db_connection,
    initialize_database,
    list_save_files,
    seed_npcs,
    seed_spells,
    set_db_file,
)
from dnd.character_creator import run_character_creation, clear_screen, choose_companion_count
from dnd.data import STORE_INVENTORY # Import STORE_INVENTORY
from dnd.cli import CommandHandler
from dnd.ui import banner, prompt_marker, section, speaker, style, wrap_text

def main():
    """Main function to run the D&D game."""
    
    player_name = "Player" # Default name
    session_id = None

    # --- Game Setup ---
    selected_save = choose_save_file()
    set_db_file(selected_save)
    is_new_save = not os.path.exists(selected_save)
    initialize_database()

    if is_new_save:
        seed_spells()
        session_id = create_game_session()
        player_name = run_character_creation()
        companion_count = choose_companion_count(len(NPC_ARCHETYPES))
        seed_npcs(companion_count)
    else:
        session_id = ensure_game_session()

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
                system_prompt=archetype['system_prompt'],
                session_id=session_id,
            )
            companion_descriptions.append(f"{archetype['name']} the {archetype['class'].lower()}")
    
    dm = DungeonMaster(session_id=session_id)
    dm.update_world_state("player_name", player_name)
    handler = CommandHandler(player_sheet, character_sheets, npcs, dm)

    # --- Game Start ---
    clear_screen()
    print(banner("D&D Text Adventure"))
    print(style("Welcome to your D&D adventure!", "gold", bold=True))
    print(f"{style('Hero', 'cyan', bold=True)} {player_name}")
    print(f"{section('Character Sheet')}\n{player_sheet}")
    if companion_descriptions:
        print(f"{style('Companions', 'magenta', bold=True)} {', and '.join(companion_descriptions)}.")
    else:
        print(style("You begin this adventure without companions.", "gray"))
    print(style("─" * 40, "gray"))
    print(style(wrap_text(dm.generate_opening_scene(player_sheet, npcs)), "parchment"))
    handler.print_turn_status()
    handler.print_suggested_actions()

    # --- Main Game Loop ---
    while True:
        try:
            user_input = input(f"\n{prompt_marker()}")
            if user_input.lower() in ["quit", "exit"]:
                print(style("The adventure ends... for now.", "red", bold=True))
                break

            if user_input.lower().startswith("/") or user_input.lower().startswith("ask "):
                skip_dm, user_input = handler.handle(user_input)
                if skip_dm:
                    continue
                if not user_input:
                    continue

            print(f"\n{speaker('DM', 'gold')} ", end="")
            response = dm.generate_response(user_input, player_sheet, npcs)
            scene_memory = build_scene_memory(user_input, response)
            dm.update_world_state("scene_summary", scene_memory)
            for npc in npcs.values():
                npc.remember_scene(scene_memory)

            # Check for level up
            if "<level_up />" in response:
                print(f"\n{style('*** LEVEL UP! ***', 'green', bold=True)}")
                for sheet in character_sheets.values():
                    sheet.level_up()
            
            # Check for gold award
            gold_match = re.search(r'<award_gold amount="(\d+)"(?: reason="[^"]*")? />', response)
            if gold_match:
                amount = int(gold_match.group(1))
                player_sheet.add_gold(amount)
                # Remove tag from DM response for cleaner display
                response = re.sub(r'<award_gold amount="(\d+)"(?: reason="[^"]*")? />', '', response).strip()

            handler.advance_turn()
            handler.print_turn_status()
            handler.print_suggested_actions()


        except (KeyboardInterrupt, EOFError):
            print(f"\n{style('The adventure ends... for now.', 'red', bold=True)}")
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

def build_scene_memory(user_input: str, response: str) -> str:
    clean_response = " ".join(response.split())
    if len(clean_response) > 220:
        clean_response = clean_response[:217] + "..."
    return f"Player action: {user_input} | Outcome: {clean_response}"

def choose_save_file() -> str:
    saves = list_save_files()
    if not saves:
        return create_save_path()

    while True:
        clear_screen()
        print(banner("Save Files"))
        for index, save_path in enumerate(saves, start=1):
            print(f"{style(str(index) + '.', 'cyan', bold=True)} {style(format_save_label(save_path), 'silver', bold=True)}")
        print(style("N.", "green", bold=True) + " " + style("Create a new save", "silver"))
        print(style("D.", "red", bold=True) + " " + style("Delete an existing save", "silver"))
        choice = input(prompt_marker()).strip().lower()

        if choice == "n":
            save_name = input(f"{style('Enter a save name (leave blank for timestamp)', 'silver')} {prompt_marker()}").strip()
            return create_save_path(save_name or None)

        if choice == "d":
            delete_choice = input(f"{style('Enter the number of the save to delete', 'silver')} {prompt_marker()}").strip()
            if delete_choice.isdigit():
                idx = int(delete_choice) - 1
                if 0 <= idx < len(saves):
                    delete_save_file(str(saves[idx]))
                    saves = list_save_files()
            continue

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(saves):
                return str(saves[idx])

if __name__ == "__main__":
    main()
