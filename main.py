import re
import os
import json
import time
from pathlib import Path
from datetime import datetime
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
    choose_session_round_budget,
    choose_spectator_settings,
)
from dnd.data import MAX_LEVEL, SPELL_DATA, CLASS_DATA, STORE_INVENTORY
from dnd.cli import CommandHandler
from dnd.completion import enable_command_completion
from dnd.spectator import build_scene_memory, build_turn_context, detect_scene_stall, extract_open_threads, is_fallback_action, _strip_fallback_marker
from dnd.transcript import TranscriptWriter
from dnd.ui import apply_base_style, banner, highlight_quotes, prompt_marker, section, speaker, style, wrap_text


def _build_player_agent(player_sheet, dm):
    from dnd.npc.agent import NPCAgent
    items = player_sheet.equipped_items
    item_str = ", ".join(items) if items else "basic equipment"
    system_prompt = (
        f"You are {player_sheet.name}, a {player_sheet.class_name}. "
        f"You are a capable adventurer exploring a dangerous world. "
        f"Your equipped items include: {item_str}. "
        f"Act decisively and in character. Speak briefly and concretely."
    )
    return NPCAgent(
        name=player_sheet.name,
        class_name=player_sheet.class_name,
        system_prompt=system_prompt,
        session_id=dm.session_id,
    )


def should_wait_before_spectator_turn(actor_type: str) -> bool:
    return actor_type != "player"


def derive_story_phase(current_round: int, target_rounds: int) -> str:
    if target_rounds <= 1:
        return "resolution"
    progress_ratio = current_round / target_rounds
    if progress_ratio <= 0.25:
        return "opening"
    if progress_ratio <= 0.70:
        return "midgame"
    if progress_ratio <= 0.90:
        return "climax"
    return "resolution"


def create_transcript_path(save_path: str, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    save_label = format_save_label(Path(save_path))
    return Path("logs") / f"{save_label}_{timestamp}.md"



def choose_transcript_logging(save_path: str) -> "TranscriptWriter | None":
    choice = input(f"{style('Save a transcript for this session?', 'silver')} {style('[y/N]', 'cyan')} {prompt_marker()}").strip().lower()
    if choice not in {"y", "yes"}:
        return None
    transcript_path = create_transcript_path(save_path)
    if os.getenv("USE_CLAUDE_CLI", "").lower() == "true":
        model = os.getenv("CLAUDE_CLI_MODEL", "claude-sonnet-4-6")
    else:
        model = os.getenv("OLLAMA_MODEL", "unknown")
    return TranscriptWriter(path=transcript_path, save_path=save_path, model=model).start()


def run_level_up_menu(player_sheet: "CharacterSheet") -> None:
    """Interactive level-up flow: rolls HP, optionally adds a spell."""
    print(f"\n{section('Level Up')}")
    new_level = player_sheet.level + 1
    print(style(f"You advance to level {new_level}!", "green", bold=True))

    # Roll HP: "1" + hit_die_type (e.g. "d8") → "1d8", then add CON modifier, minimum 1
    con_mod = player_sheet.ability_modifiers.get("CON", 0)
    roll_result, roll_desc = roll_dice("1" + player_sheet.hit_die_type)
    hp_increase = max(1, roll_result + con_mod)
    print(style(f"HP increase: {roll_desc} + CON({con_mod:+d}) = {hp_increase}", "cyan"))
    player_sheet.level_up(hp_increase)

    # Offer spell selection for spellcasting classes
    class_info = CLASS_DATA.get(player_sheet.class_name, {})
    available_spells = class_info.get("spells", []) + class_info.get("cantrips", [])
    known_names = {s["name"] for s in player_sheet.spells} if player_sheet.spells else set()
    learnable = [s for s in available_spells if s not in known_names]
    if learnable:
        print(style("\nAvailable spells to learn:", "silver"))
        for i, spell_name in enumerate(learnable, 1):
            spell = SPELL_DATA.get(spell_name, {})
            level_label = "Cantrip" if spell.get("level", 0) == 0 else f"Level {spell.get('level', '?')}"
            print(f"  [{i}] {spell_name} ({level_label}) — {spell.get('description', '')[:60]}")
        print("  [0] Skip")
        choice = input(style("Choose a spell to learn (number): ", "cyan")).strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(learnable):
                chosen = learnable[idx]
                player_sheet.learn_spell(chosen)
                print(style(f"You learned {chosen}!", "green"))


def run_between_quest_menu(
    player_sheet: "CharacterSheet",
    handler: "CommandHandler",
    level_eligible: bool = True,
) -> None:
    """Guided between-quest menu: level up → rest → shop."""
    print(f"\n{section('Between Quests')}")
    print(style("Time passes. Before your next adventure...", "silver", italic=True))

    # Level Up
    if level_eligible:
        run_level_up_menu(player_sheet)

    # Rest
    rest_choice = input(style("\nDo you want to take a long rest? [y/N] ", "cyan") + prompt_marker()).strip().lower()
    if rest_choice in {"y", "yes"}:
        player_sheet.take_long_rest()

    # Shop
    shop_choice = input(style("\nDo you want to visit the shop? [y/N] ", "cyan") + prompt_marker()).strip().lower()
    if shop_choice in {"y", "yes"}:
        handler.handle("/shop")
        print(style("Enter /buy <item> to purchase, or press Enter to leave.", "silver", dim=True, italic=True))
        while True:
            buy_input = input(f"\n{prompt_marker()}").strip()
            if not buy_input or buy_input.lower() in {"done", "exit", "leave"}:
                break
            if buy_input.startswith("/buy"):
                handler.handle(buy_input)
            else:
                print(style("Use /buy <item name> to purchase.", "red"))

    input(style("\nPress Enter to begin your next quest...", "gold", bold=True) + prompt_marker())


def run_post_quest_flow(
    dm: "DungeonMaster",
    npcs: dict,
    player_sheet: "CharacterSheet",
    handler: "CommandHandler",
    transcript=None,
) -> None:
    """
    Full post-quest transition: epilogue → campaign summary → downtime →
    between-quest menu → reset → new opening + arc.
    Called when story_complete fires OR round limit is reached.
    """
    # 1. Epilogue
    print(f"\n{speaker('DM', 'gold')} ", end="")
    epilogue = dm.generate_epilogue()
    print(apply_base_style(highlight_quotes(wrap_text(epilogue)), "parchment"))
    if transcript:
        transcript.write_dm_response(epilogue, 0)

    # 2. Campaign summary (persists to DB via update_world_state)
    dm.generate_campaign_summary()

    # 3. Downtime narration
    downtime = dm.generate_downtime_scene()
    print(f"\n{style('— Downtime —', 'silver', italic=True)}")
    print(apply_base_style(highlight_quotes(wrap_text(downtime)), "parchment"))
    if transcript:
        transcript.write_dm_response(downtime, 0)

    # 4. Between-quest menu
    level_eligible = player_sheet.level < MAX_LEVEL
    run_between_quest_menu(player_sheet, handler, level_eligible=level_eligible)

    # 5. Reset world state and clear NPC in-memory state
    dm.reset_for_new_quest()
    for npc in npcs.values():
        npc.history = []
        npc.recent_actions = []
    handler.round_number = 1

    # 6. Generate new opening and arc with campaign context
    campaign_history = list(dm.world_state.get("campaign_history", []) or [])
    campaign_context = campaign_history[-1] if campaign_history else ""
    opening_scene = dm.generate_opening_scene(player_sheet, npcs, campaign_context=campaign_context)
    dm.generate_arc(opening_scene, campaign_context=campaign_context)
    if transcript:
        transcript.write_opening_scene(opening_scene, elapsed=0)
    print(apply_base_style(highlight_quotes(wrap_text(opening_scene)), "parchment"))
    handler.print_turn_status()
    handler.print_suggested_actions()


def main():
    """Main function to run the D&D game."""
    
    player_name = "Player" # Default name
    session_id = None
    spectator_mode = False
    target_rounds = None
    spectator_pause_seconds = 0.0
    setup_completed = False
    transcript = None

    # --- Game Setup ---
    selected_save = choose_save_file()
    transcript = choose_transcript_logging(selected_save)
    if transcript is not None:
        print(style(f"Transcript logging enabled.", "green", bold=True))
    try:
        set_db_file(selected_save)
        is_new_save = not os.path.exists(selected_save)
        initialize_database()
        touch_save_accessed_at()

        if is_new_save:
            seed_spells()
            session_id = create_game_session()
            spectator_mode, target_rounds, spectator_pause_seconds, player_name = run_initial_setup()
            setup_completed = True
        else:
            session_id = ensure_game_session()
            conn = get_db_connection()
            player_row = conn.execute("SELECT name FROM characters WHERE is_player = 1").fetchone()
            conn.close()
            if player_row is None:
                print(style("This save has no finished player setup yet. Resuming setup now.", "silver", dim=True, italic=True))
                seed_spells()
                spectator_mode, target_rounds, spectator_pause_seconds, player_name = run_initial_setup()
                setup_completed = True

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
        if setup_completed:
            dm.update_world_state("spectator_mode", spectator_mode)
            dm.update_world_state("target_rounds", target_rounds)
            dm.update_world_state("spectator_pause_seconds", spectator_pause_seconds)
        else:
            spectator_mode = bool(dm.world_state.get("spectator_mode", False))
            target_rounds = dm.world_state.get("target_rounds")
            if target_rounds is None:
                target_rounds = dm.world_state.get("spectator_max_rounds")
            if target_rounds is None:
                target_rounds = dm.world_state.get("spectator_max_turns")
            if target_rounds is None:
                target_rounds = 20
                dm.update_world_state("target_rounds", target_rounds)
            spectator_pause_seconds = float(dm.world_state.get("spectator_pause_seconds", 0.0) or 0.0)
        handler = CommandHandler(player_sheet, character_sheets, npcs, dm)
        enable_command_completion(handler)
        player_agent = _build_player_agent(player_sheet, dm) if spectator_mode else None

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
            limit_text = f"{target_rounds} rounds max"
            print(style(f"Spectator mode is on: {mode_text}, {limit_text}.", "silver", dim=True, italic=True))
        else:
            print(style(f"Session length: {target_rounds} rounds.", "silver", dim=True, italic=True))
        print(style("─" * 40, "gray"))
        _t0 = time.time()
        opening_scene = dm.generate_opening_scene(player_sheet, npcs)
        _opening_elapsed = time.time() - _t0
        dm.generate_arc(opening_scene)
        if transcript:
            transcript.write_opening_scene(opening_scene, elapsed=_opening_elapsed)
        print(apply_base_style(highlight_quotes(wrap_text(opening_scene)), "parchment"))
        handler.print_turn_status()
        handler.print_suggested_actions()

        # --- Main Game Loop ---
        while True:
            try:
                if spectator_mode:
                    if handler.round_number > target_rounds:
                        run_post_quest_flow(dm, npcs, player_sheet, handler, transcript=transcript)
                        continue
                    actor = handler.current_turn_actor
                    should_pause = should_wait_before_spectator_turn(actor["type"])
                    if spectator_pause_seconds == 0 and should_pause:
                        advance = input(f"\n{style('Spectator mode: press Enter for next turn or type quit', 'silver', dim=True, italic=True)} {prompt_marker()}")
                        if advance.strip().lower() in ["quit", "exit"]:
                            print(style("The adventure ends... for now.", "red", bold=True))
                            break
                    elif spectator_pause_seconds > 0 and should_pause:
                        print(style(f"Spectator mode: next turn in {spectator_pause_seconds:g}s", "silver", dim=True, italic=True))
                        time.sleep(spectator_pause_seconds)
                    if transcript and actor.get("type") == "player":
                        transcript.write_round_header(handler.round_number)
                    action = run_spectator_turn(handler, dm, player_sheet, player_agent, transcript=transcript)
                    if action is None:
                        continue
                    if action:
                        story_complete = process_dm_turn(action, dm, npcs, player_sheet, character_sheets, handler, transcript=transcript)
                        if story_complete:
                            run_post_quest_flow(dm, npcs, player_sheet, handler, transcript=transcript)
                            continue
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

                story_complete = process_dm_turn(user_input, dm, npcs, player_sheet, character_sheets, handler, transcript=transcript)
                if story_complete:
                    run_post_quest_flow(dm, npcs, player_sheet, handler, transcript=transcript)
                    continue


            except (KeyboardInterrupt, EOFError):
                print(f"\n{style('The adventure ends... for now.', 'red', bold=True)}")
                break

            update_condition_durations()
    finally:
        if transcript is not None:
            transcript.stop()

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

def process_dm_turn(user_input: str, dm, npcs, player_sheet, character_sheets, handler, transcript=None) -> bool:
    print(f"\n{speaker('DM', 'gold')} ", end="")
    _t0 = time.time()
    raw_response, cleaned_response = dm.generate_response(user_input, player_sheet, npcs)
    _dm_elapsed = time.time() - _t0
    response = raw_response  # used below for tag detection
    if transcript:
        transcript.write_dm_response(cleaned_response, _dm_elapsed)
    previous_scene_memory = str(dm.world_state.get("scene_summary", "") or "")
    if not is_fallback_action(user_input):
        recent_party_actions = list(dm.world_state.get("recent_party_actions", []))
        recent_party_actions.append(f"{player_sheet.name} acted: {_strip_fallback_marker(user_input)}")
        dm.update_world_state("recent_party_actions", recent_party_actions[-6:])
    scene_memory = build_scene_memory(user_input, response)
    dm.update_world_state("scene_summary", scene_memory)
    new_progress_events = dm.world_state.get("last_progress_events", [])
    scene_stall_count = int(dm.world_state.get("scene_stall_count", 0) or 0)
    previous_threads = str(dm.world_state.get("previous_open_threads", "") or "")
    current_threads = extract_open_threads(str(dm.world_state.get("story_summary", "") or ""))
    if detect_scene_stall(
        previous_scene_memory, scene_memory, new_progress_events,
        previous_threads=previous_threads, current_threads=current_threads,
    ):
        scene_stall_count += 1
    else:
        scene_stall_count = 0
    dm.update_world_state("scene_stall_count", scene_stall_count)
    dm.update_world_state("previous_open_threads", current_threads)
    for npc in npcs.values():
        npc.remember_scene(scene_memory)

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
    return dm.story_is_complete()


def run_spectator_turn(handler, dm, player_sheet, player_agent, transcript=None) -> str | None:
    actor = handler.current_turn_actor
    if actor["type"] == "player":
        scene_summary = dm.world_state.get("scene_summary", "No scene summary recorded yet.")
        recent_party_actions = list(dm.world_state.get("recent_party_actions", []))
        turn_context = build_turn_context(
            dm.world_state,
            actor_name=player_sheet.name,
            actor_type="player",
            scene_summary=scene_summary,
            recent_party_actions=recent_party_actions,
        )
        action = player_agent.generate_turn_action(
            game_context=list(dm.history),
            scene_summary=scene_summary,
            recent_party_actions=recent_party_actions,
            turn_context=turn_context,
            actor_type="player",
        )
        display_action = _strip_fallback_marker(action) if action else action
        if transcript and display_action:
            transcript.write_player_action(player_sheet.name, display_action)
        print(f"\n{speaker(player_sheet.name, 'cyan')} {wrap_text(display_action)}")
        return action
    if actor["type"] == "companion":
        _t0 = time.time()
        handler.handle("/npcturn")
        if transcript:
            transcript.write_companion_action(
                actor["name"],
                handler.last_companion_response,
                elapsed=time.time() - _t0,
            )
        return None
    skip_dm, prompt = handler.handle("/enemyturn")
    if skip_dm:
        return None
    return prompt

def run_initial_setup() -> tuple[bool, int, float, str]:
    spectator_mode = choose_game_mode()
    target_rounds = choose_session_round_budget()
    spectator_pause_seconds = 0.0
    if spectator_mode:
        spectator_pause_seconds = choose_spectator_settings()
    player_name = run_character_creation()
    companion_count = choose_companion_count(len(NPC_ARCHETYPES))
    seed_npcs(companion_count)
    return spectator_mode, target_rounds, spectator_pause_seconds, player_name


def choose_save_file() -> str:
    saves = list_save_files()
    if not saves:
        save_name = input(f"{style('Name your adventure (leave blank for timestamp)', 'silver')} {prompt_marker()}").strip()
        return create_save_path(save_name or None)

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
