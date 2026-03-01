import os
from dnd.dm.agent import DungeonMaster
from dnd.dm.prompts import ADVENTURE_START_PROMPT
from dnd.npc.agent import NPCAgent
from dnd.npc.prompts import NPC_ARCHETYPES
from dnd.game import roll_dice
from dnd.character import CharacterSheet
from dnd.database import initialize_database, get_db_connection, seed_npcs, seed_spells, DB_FILE
from dnd.character_creator import run_character_creation, clear_screen

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
        player_name = conn.execute("SELECT name FROM characters WHERE level = 1").fetchone()['name']
    
    npc_names = [row['name'] for row in conn.execute("SELECT name FROM characters WHERE name != ?", (player_name,)).fetchall()]
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
                system_prompt=archetype['system_prompt']
            )
            companion_descriptions.append(f"{archetype['name']} the {archetype['class'].lower()}")
    
    dm = DungeonMaster()

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

            if user_input.lower().startswith("/"):
                # Handle commands
                parts = user_input.split(" ", 1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if command == "/roll":
                    try:
                        total, explanation = roll_dice(args)
                        print(explanation)
                    except ValueError as e:
                        print(e)
                elif command == "/sheet":
                    print(player_sheet)
                elif command == "/testhp":
                    try:
                        player_sheet.update_hp(int(args))
                    except (ValueError, IndexError):
                        print("Usage: /testhp <amount>")
                elif command == "/attack":
                    weapon_name = args.strip().title()
                    if not weapon_name:
                        print("Usage: /attack <weapon name>")
                    elif weapon_name in player_sheet.inventory:
                        bonus = player_sheet.get_attack_bonus(weapon_name)
                        damage = player_sheet.get_damage_roll(weapon_name)
                        print(f"Attacking with {weapon_name}:")
                        print(f"  Attack Bonus: 1d20 + {bonus}")
                        print(f"  Damage: {damage}")
                    else:
                        print(f"You do not have a '{weapon_name}' in your inventory.")
                elif command == "/cast":
                    spell_name = args.strip().title()
                    known_spell = next((s for s in player_sheet.spells if s['name'].title() == spell_name), None)
                    
                    if not spell_name:
                        print("Usage: /cast <spell name>")
                    elif known_spell:
                        if player_sheet.cast_spell(known_spell['level']):
                            print(f"You cast {spell_name}.")
                            # Now, tell the DM about it
                            user_input = f"I cast the {spell_name} spell."
                            # This will fall through to the DM response logic below
                        else:
                            print(f"You don't have any level {known_spell['level']} spell slots left.")
                            continue # Don't send to DM
                    else:
                        print(f"You don't know the spell '{spell_name}'.")
                        continue # Don't send to DM
                else:
                    print(f"Unknown command: {command}")
                continue

            # If we are here after a /cast, the user_input has been modified
            # to inform the DM of the action.

            if user_input.lower().startswith("ask "):
                parts = user_input.split(" ", 2)
                if len(parts) < 3:
                    print("To talk to an NPC, use 'ask <name> <message>'")
                    continue
                
                npc_name = parts[1].lower()
                message = parts[2]
                
                if npc_name in npcs:
                    print(f"\n{npcs[npc_name].name}: ", end='')
                    npcs[npc_name].generate_response(message, dm.history)
                else:
                    print(f"You don't have a companion named {npc_name}.")
                continue

            print("\nDM: ", end='')
            response = dm.generate_response(user_input, player_sheet)

            if "<level_up />" in response:
                print("\n--- LEVEL UP! ---")
                for sheet in character_sheets.values():
                    sheet.level_up()
                print("-----------------")

        except (KeyboardInterrupt, EOFError):
            print("\nThe adventure ends... for now.")
            break

if __name__ == "__main__":
    main()