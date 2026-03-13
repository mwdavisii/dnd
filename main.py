import re
import os
import json
import time
from pathlib import Path
from dnd.dm.agent import DungeonMaster
from dnd.npc.agent import NPCAgent
from dnd.npc.prompts import NPC_ARCHETYPES
from dnd.player_agent import AutoPlayerAgent
from dnd.game import roll_dice
from dnd.character import CharacterSheet
from dnd.database import (
    DB_FILE,
    create_game_session,
    create_save_path,
    delete_save_file,
    ensure_game_session,
    format_save_label,
    get_save_metadata,
    get_db_connection,
    initialize_database,
    list_save_files,
    seed_npcs,
    seed_spells,
    set_db_file,
    touch_save_accessed_at,
)
from dnd.character_creator import (
    run_character_creation,
    clear_screen,
    choose_companion_count,
    choose_game_mode,
    choose_spectator_settings,
)
from dnd.data import STORE_INVENTORY # Import STORE_INVENTORY
from dnd.cli import CommandHandler
from dnd.completion import enable_command_completion
from dnd.ui import apply_base_style, banner, highlight_quotes, prompt_marker, section, speaker, style, wrap_text

def main():
    """Main function to run the D&D game."""
    
    player_name = "Player" # Default name
    session_id = None
    spectator_mode = False
    spectator_max_turns = None
    spectator_pause_seconds = 0.0

    # --- Game Setup ---
    selected_save = choose_save_file()
    set_db_file(selected_save)
    is_new_save = not os.path.exists(selected_save)
    initialize_database()
    touch_save_accessed_at()

    if is_new_save:
        seed_spells()
        session_id = create_game_session()
        spectator_mode, spectator_max_turns, spectator_pause_seconds, player_name = run_initial_setup()
    else:
        session_id = ensure_game_session()
        conn = get_db_connection()
        player_row = conn.execute("SELECT name FROM characters WHERE is_player = 1").fetchone()
        conn.close()
        if player_row is None:
            print(style("This save has no finished player setup yet. Resuming setup now.", "silver", dim=True, italic=True))
            seed_spells()
            spectator_mode, spectator_max_turns, spectator_pause_seconds, player_name = run_initial_setup()

    # --- Dynamic Character Loading ---
    conn = get_db_connection()
    # Get player name if not already set from character creation
    if player_name == "Player":
        player_row = conn.execute("SELECT name FROM characters WHERE is_player = 1").fetchone()
        if player_row is None:
            raise RuntimeError("No player character exists for this save. Character setup may not have completed.")
        player_name = player_row['name']

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
    if is_new_save:
        dm.update_world_state("spectator_mode", spectator_mode)
        dm.update_world_state("spectator_max_turns", spectator_max_turns)
        dm.update_world_state("spectator_pause_seconds", spectator_pause_seconds)
    else:
        spectator_mode = bool(dm.world_state.get("spectator_mode", False))
        spectator_max_turns = dm.world_state.get("spectator_max_turns")
        spectator_pause_seconds = float(dm.world_state.get("spectator_pause_seconds", 0.0) or 0.0)
    handler = CommandHandler(player_sheet, character_sheets, npcs, dm)
    enable_command_completion(handler)
    player_agent = AutoPlayerAgent(player_sheet) if spectator_mode else None
    spectator_turns_taken = 0

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
    if spectator_mode:
        mode_text = "manual step-through" if spectator_pause_seconds == 0 else f"{spectator_pause_seconds:g}s autoplay"
        limit_text = "unlimited turns" if spectator_max_turns is None else f"{spectator_max_turns} turns max"
        print(style(f"Spectator mode is on: {mode_text}, {limit_text}.", "silver", dim=True, italic=True))
    print(style("─" * 40, "gray"))
    print(apply_base_style(highlight_quotes(wrap_text(dm.generate_opening_scene(player_sheet, npcs))), "parchment"))
    handler.print_turn_status()
    handler.print_suggested_actions()

    # --- Main Game Loop ---
    while True:
        try:
            if spectator_mode:
                if spectator_max_turns is not None and spectator_turns_taken >= spectator_max_turns:
                    print(style("Spectator run finished: reached the configured turn limit.", "silver", dim=True, italic=True))
                    break
                if spectator_pause_seconds == 0:
                    advance = input(f"\n{style('Spectator mode: press Enter for next turn or type quit', 'silver', dim=True, italic=True)} {prompt_marker()}")
                    if advance.strip().lower() in ["quit", "exit"]:
                        print(style("The adventure ends... for now.", "red", bold=True))
                        break
                else:
                    print(style(f"Spectator mode: next turn in {spectator_pause_seconds:g}s", "silver", dim=True, italic=True))
                    time.sleep(spectator_pause_seconds)
                action = run_spectator_turn(handler, dm, player_sheet, player_agent)
                spectator_turns_taken += 1
                if action is None:
                    continue
                if action:
                    process_dm_turn(action, dm, npcs, player_sheet, character_sheets, handler)
                continue

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
            elif not handler.player_can_act():
                continue

            process_dm_turn(user_input, dm, npcs, player_sheet, character_sheets, handler)


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


def process_dm_turn(user_input: str, dm, npcs, player_sheet, character_sheets, handler) -> None:
    print(f"\n{speaker('DM', 'gold')} ", end="")
    response = dm.generate_response(user_input, player_sheet, npcs)
    recent_party_actions = list(dm.world_state.get("recent_party_actions", []))
    recent_party_actions.append(f"{player_sheet.name} acted: {user_input}")
    dm.update_world_state("recent_party_actions", recent_party_actions[-6:])
    scene_memory = build_scene_memory(user_input, response)
    dm.update_world_state("scene_summary", scene_memory)
    for npc in npcs.values():
        npc.remember_scene(scene_memory)

    new_progress_events = dm.world_state.get("last_progress_events", [])
    reward_history = list(dm.world_state.get("reward_history", []))
    if "<level_up />" in response and new_progress_events:
        level_reward_key = f"level:{new_progress_events[0]}"
        if level_reward_key not in reward_history:
            print(f"\n{style('*** LEVEL UP! ***', 'green', bold=True)}")
            for sheet in character_sheets.values():
                sheet.level_up()
            reward_history.append(level_reward_key)
            dm.update_world_state("reward_history", reward_history[-20:])
    elif "<level_up />" in response:
        print(style("Repeated level-up tag ignored because no new milestone was detected.", "gray", dim=True, italic=True))

    gold_match = re.search(r'<award_gold amount="(\d+)"(?: reason="[^"]*")? />', response)
    if gold_match:
        amount = int(gold_match.group(1))
        reason_match = re.search(r'<award_gold amount="\d+"(?: reason="([^"]*)")? />', response)
        reason = reason_match.group(1) if reason_match and reason_match.group(1) else "unlabeled_reward"
        reward_key = f"gold:{reason}"
        if reward_key not in reward_history:
            player_sheet.add_gold(amount)
            reward_history.append(reward_key)
            dm.update_world_state("reward_history", reward_history[-20:])
        else:
            print(style(f"Repeated gold award ignored for '{reason}'.", "gray", dim=True, italic=True))

    handler.advance_turn()
    handler.print_turn_status()
    handler.print_suggested_actions()


def run_spectator_turn(handler, dm, player_sheet, player_agent) -> str | None:
    actor = handler.current_turn_actor
    if actor["type"] == "player":
        scene_summary = dm.world_state.get("scene_summary", "No scene summary recorded yet.")
        recent_party_actions = list(dm.world_state.get("recent_party_actions", []))
        action = player_agent.generate_action(scene_summary, recent_party_actions)
        print(f"\n{speaker(player_sheet.name, 'cyan')} {action}")
        return action
    if actor["type"] == "companion":
        handler.handle("/npcturn")
        return None
    skip_dm, prompt = handler.handle("/enemyturn")
    if skip_dm:
        return None
    return prompt

def run_initial_setup() -> tuple[bool, int | None, float, str]:
    spectator_mode = choose_game_mode()
    spectator_max_turns = None
    spectator_pause_seconds = 0.0
    if spectator_mode:
        spectator_max_turns, spectator_pause_seconds = choose_spectator_settings()
    player_name = run_character_creation()
    companion_count = choose_companion_count(len(NPC_ARCHETYPES))
    seed_npcs(companion_count)
    return spectator_mode, spectator_max_turns, spectator_pause_seconds, player_name


def choose_save_file() -> str:
    saves = list_save_files()
    if not saves:
        return create_save_path()

    while True:
        clear_screen()
        print(banner("Save Files"))
        for index, save_path in enumerate(saves, start=1):
            metadata = get_save_metadata(save_path)
            print(f"{style(str(index) + '.', 'cyan', bold=True)} {style(format_save_label(save_path), 'silver', bold=True)}")
            print(
                f"   {style('Created:', 'gray')} {style(metadata['created_at'], 'silver')}  "
                f"{style('Last Played:', 'gray')} {style(metadata['last_accessed_at'], 'silver')}"
            )
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
