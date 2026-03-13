# dnd/cli/__init__.py
import json
from collections import Counter
from dnd.data import HELP_TOPICS, MONSTER_DATA, RULES_REFERENCE, SPELL_DATA, STORE_INVENTORY, WEAPON_DATA
from dnd.game import roll_dice
from dnd.database import get_db_connection
from dnd.ui import speaker, style

COMMAND_NAMES = [
    "/addcondition",
    "/attack",
    "/ask",
    "/buy",
    "/cast",
    "/encounter",
    "/endturn",
    "/enemyturn",
    "/equip",
    "/help",
    "/inventory",
    "/journal",
    "/longrest",
    "/map",
    "/nextturn",
    "/npcturn",
    "/rage",
    "/removecondition",
    "/roll",
    "/rules",
    "/sheet",
    "/shop",
    "/shortrest",
    "/sneakattack",
    "/teach",
    "/testhp",
    "/turn",
    "/unequip",
    "/unrage",
    "/worldstate",
]

ENCOUNTER_ENEMY_SUGGESTIONS = sorted(MONSTER_DATA)


class CommandHandler:
    def __init__(self, player_sheet, character_sheets, npcs, dm):
        self.player_sheet = player_sheet
        self.character_sheets = character_sheets
        self.npcs = npcs
        self.dm = dm
        self.teaching_mode = False
        self.turn_order = [self.player_sheet.name] + [npc.name for npc in self.npcs.values()]
        self.turn_index = 0
        self.round_number = int(self.dm.world_state.get("current_round", 1) or 1)
        self.encounter = None
        self._sync_story_pacing()

    def handle(self, user_input: str) -> tuple[bool, str]:
        if user_input.lower().startswith("ask "):
            return self._handle_ask(user_input)
        return self._handle_command(user_input)

    def _handle_ask(self, user_input: str) -> tuple[bool, str]:
        normalized_input = user_input[1:] if user_input.startswith("/") else user_input
        parts = normalized_input.split(" ", 2)
        if len(parts) < 3:
            print("To talk to an NPC, use 'ask <name> <message>'")
            return (True, "")

        npc_name = parts[1].lower()
        message = parts[2]

        if npc_name in self.npcs:
            print(f"\n{speaker(self.npcs[npc_name].name, 'magenta')} ", end="")
            response = self.npcs[npc_name].generate_response(message, self.dm.history)
            if response:
                self.dm.add_history("assistant", f"{self.npcs[npc_name].name}: {response}")
            print(style("Conversation does not end your turn.", "gray", dim=True, italic=True))
            self.print_turn_status()
            self.print_suggested_actions()
        else:
            print(style(f"You don't have a companion named {npc_name}.", "red"))
        return (True, "")

    def _handle_command(self, user_input: str) -> tuple[bool, str]:
        parts = user_input.split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "/roll":
            if not args.strip():
                if self._roll_pending_request():
                    return (True, "")
                print(style("Usage: /roll <dice|ability>. Examples: /roll d20, /roll dex, /roll dex save", "red"))
                return (True, "")
            if self._roll_contextual_request(args.strip()):
                return (True, "")
            try:
                total, explanation = roll_dice(args)
                print(explanation)
            except ValueError as e:
                print(style(str(e), "red"))
            return (True, "")

        elif command == "/sheet":
            self.player_sheet.refresh_cache()
            print(self.player_sheet)
            if self.teaching_mode:
                print("Teaching: AC is the number enemies must meet or beat to hit you. Attack and spell bonuses are added to your d20 rolls.")
            return (True, "")

        elif command == "/testhp":
            try:
                self.player_sheet.update_hp(int(args))
            except (ValueError, IndexError):
                print(style("Usage: /testhp <amount>", "red"))
            return (True, "")

        elif command == "/attack":
            self._auto_start_pending_encounter_for_attack()
            if not self._player_can_act():
                return (True, "")
            is_sneak_attack = "--sneak" in args
            weapon_name = args.replace("--sneak", "").strip().title()
            if not weapon_name:
                print(style("Usage: /attack <weapon name> [--sneak]", "red"))
            elif weapon_name in [item for item, _ in self.player_sheet.inventory_items]:
                breakdown = self.player_sheet.get_attack_breakdown(weapon_name, is_sneak_attack)
                self._print_attack_breakdown(breakdown)
                if self.teaching_mode and breakdown:
                    print("Teaching: Roll the d20 and add the total to-hit bonus. If that meets or beats the target's AC, roll the listed damage.")
                action = f"I attack with my {weapon_name}"
                if self.encounter:
                    enemies = self.dm.world_state.get("encounter_enemies", "")
                    if enemies:
                        action += f" against {enemies.split(',')[0].strip()}"
                if is_sneak_attack:
                    action += " with a sneak attack"
                return (False, action + ".")
            else:
                print(style(f"You do not have a '{weapon_name}' in your inventory.", "red"))
            return (True, "")

        elif command == "/ask":
            if not args:
                workflow_input = self._prompt_for_ask()
                if not workflow_input:
                    print(style("Conversation cancelled.", "red"))
                    return (True, "")
                return self._handle_ask(workflow_input)
            return self._handle_ask(f"ask {args}")

        elif command == "/sneakattack":
            weapon_name = "Shortsword"
            if self.player_sheet.class_name == "Rogue" and weapon_name in [item for item, _ in self.player_sheet.inventory_items]:
                breakdown = self.player_sheet.get_attack_breakdown(weapon_name, is_sneak_attack=True)
                print(f"Performing a Sneak Attack with {weapon_name}:")
                self._print_attack_breakdown(breakdown, include_header=False)
                if self.teaching_mode and breakdown:
                    print("Teaching: Sneak Attack adds extra damage when rogue conditions are met; the attack roll itself still uses the same to-hit bonus.")
            else:
                print(style("You can't perform a sneak attack.", "red"))
            return (True, "")

        elif command == "/cast":
            spell_name, cast_target = self._parse_spell_and_target(args.strip())
            known_spell = next((s for s in self.player_sheet.spells if s['name'].title() == spell_name), None) if spell_name else None
            if not spell_name:
                print(style("Usage: /cast <spell name>", "red"))
                return (True, "")
            elif known_spell:
                if self._is_offensive_spell(spell_name):
                    self._auto_start_pending_encounter_for_attack()
                if not self._player_can_act():
                    return (True, "")
                self._print_spell_breakdown(spell_name)
                if self.teaching_mode:
                    if known_spell["level"] == 0:
                        print("Teaching: Cantrips can be cast freely. Use the spell attack bonus if the spell asks for an attack roll, or the save DC if the target rolls a save.")
                    else:
                        print("Teaching: Leveled spells spend a spell slot. The save DC is what enemies try to beat on saving throws; the spell attack bonus is what you add to attack-roll spells.")
                if self.player_sheet.cast_spell(known_spell['level'], known_spell['name']):
                    print(style(f"You cast {spell_name}.", "green", bold=True))
                    if cast_target:
                        return (False, f"I cast the {spell_name} spell at {cast_target}.")
                    return (False, f"I cast the {spell_name} spell.")
                else:
                    print(style(f"You don't have any level {known_spell['level']} spell slots left.", "red"))
                    return (True, "")
            else:
                print(style(f"You don't know the spell '{spell_name}'.", "red"))
                return (True, "")

        elif command == "/teach":
            mode = args.strip().lower()
            if mode in ("", "toggle"):
                self.teaching_mode = not self.teaching_mode
            elif mode in ("on", "off"):
                self.teaching_mode = mode == "on"
            elif mode == "status":
                pass
            else:
                print(style("Usage: /teach [on|off|toggle|status]", "red"))
                return (True, "")
            state = "on" if self.teaching_mode else "off"
            print(style(f"Teaching mode is {state}.", "green" if self.teaching_mode else "gray", bold=True))
            if self.teaching_mode:
                print("Teaching: The game will explain attack math, spell math, and suggested actions in plain language.")
            return (True, "")

        elif command == "/turn":
            self.print_turn_status()
            return (True, "")

        elif command in ("/endturn", "/nextturn"):
            self.advance_turn()
            self.print_turn_status()
            return (True, "")

        elif command == "/encounter":
            return self._handle_encounter(args.strip())

        elif command == "/enemyturn":
            if not self.encounter:
                print(style("No active encounter. Use /encounter start <enemy names> to begin one.", "red"))
                return (True, "")
            actor = self.current_turn_actor
            if actor["type"] != "enemy":
                print(style("It is not currently an enemy turn.", "red"))
                return (True, "")
            prompt = f"It is {actor['name']}'s turn in combat. Narrate their action briefly and clearly."
            print(f"Enemy turn: {style(actor['name'], 'red', bold=True)}")
            return (False, prompt)

        elif command == "/npcturn":
            actor = self.current_turn_actor
            if actor["type"] == "player":
                print(style("It is currently the player's turn.", "red"))
                return (True, "")
            if actor["type"] != "companion":
                print(style("It is not currently a companion's turn.", "red"))
                return (True, "")
            npc = self.npcs.get(actor["name"].lower())
            if not npc:
                print(style(f"{actor['name']} is not an available companion.", "red"))
                return (True, "")
            scene_summary = self.dm.world_state.get("scene_summary", "No scene summary recorded yet.")
            recent_party_actions = list(self._world_state_list("recent_party_actions"))
            print(f"\n{speaker(npc.name, 'magenta')} ", end="")
            response = npc.generate_turn_action(self.dm.history, scene_summary, recent_party_actions)
            if response:
                print(response)
                self.dm.add_history("assistant", f"{npc.name}: {response}")
                self._record_party_action(f"{npc.name} acted: {response}")
            self.advance_turn()
            self.print_turn_status()
            return (True, "")

        elif command == "/help":
            self._print_help(args.strip().lower())
            return (True, "")

        elif command == "/rules":
            self._print_rules(args.strip().lower())
            return (True, "")

        elif command == "/shop":
            print("\n--- Shop Inventory ---")
            for item, data in STORE_INVENTORY.items():
                print(f"- {item} ({data['cost']} gp): {data['description']}")
            print("----------------------")
            return (True, "")

        elif command == "/buy":
            item_name = args.strip().title()
            item_data = STORE_INVENTORY.get(item_name)
            if not item_name:
                print(style("Usage: /buy <item name>", "red"))
            elif item_data:
                cost = item_data['cost']
                if self.player_sheet.spend_gold(cost):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO inventory (character_id, item_name, quantity) VALUES (?, ?, ?)", (self.player_sheet._id, item_name, 1))
                    conn.commit()
                    conn.close()
                    self.player_sheet.refresh_cache()
                    print(style(f"You bought a {item_name}!", "green", bold=True))
            else:
                print(style(f"'{item_name}' is not available in the shop.", "red"))
            return (True, "")

        elif command == "/shortrest":
            if not args:
                print(style("Usage: /shortrest <number of Hit Dice to spend>", "red"))
                return (True, "")
            try:
                num_dice = int(args)
                self.player_sheet.take_short_rest(num_dice)
                return (False, f"I take a short rest, spending {num_dice} Hit Dice.")
            except ValueError:
                print(style("Invalid number of Hit Dice.", "red"))
                return (True, "")

        elif command == "/longrest":
            if not self._player_can_act():
                return (True, "")
            self.player_sheet.take_long_rest()
            return (False, "I take a long rest.")

        elif command == "/rage":
            if self.player_sheet.class_name == "Barbarian":
                self.player_sheet.start_rage()
            else:
                print(style("Only Barbarians can rage.", "red"))
            return (True, "")

        elif command == "/unrage":
            if self.player_sheet.class_name == "Barbarian":
                self.player_sheet.end_rage()
            else:
                print(style("Only Barbarians can be raging.", "red"))
            return (True, "")

        elif command == "/inventory":
            self.player_sheet.refresh_cache()
            self._print_inventory()
            return (True, "")

        elif command == "/journal":
            self._print_journal()
            return (True, "")

        elif command == "/map":
            self._print_map()
            return (True, "")

        elif command == "/equip":
            item_name = args.strip().title()
            if not item_name:
                print("Usage: /equip <item name>")
                return (True, "")
            elif item_name in [item for item, _ in self.player_sheet.inventory_items]:
                self.player_sheet.equip_item(item_name)
                return (False, f"I equip the {item_name}.")
            else:
                print(f"You do not have a '{item_name}' to equip.")
                return (True, "")

        elif command == "/unequip":
            item_name = args.strip().title()
            if not item_name:
                print("Usage: /unequip <item name>")
                return (True, "")
            elif item_name in [item for item, _ in self.player_sheet.inventory_items]:
                self.player_sheet.unequip_item(item_name)
                return (False, f"I unequip the {item_name}.")
            else:
                print(f"You do not have a '{item_name}' equipped or in your inventory to unequip.")
                return (True, "")

        elif command == "/addcondition":
            try:
                char_name, cond_name, duration_str = args.split(" ", 2)
                duration = int(duration_str)
            except ValueError:
                try:
                    char_name, cond_name = args.split(" ", 1)
                    duration = -1
                except ValueError:
                    print("Usage: /addcondition <character_name> <condition_name> [duration]")
                    return (True, "")
            char_sheet = self.character_sheets.get(char_name.lower())
            if char_sheet:
                char_sheet.add_condition(cond_name, duration)
                char_sheet.refresh_cache()
            else:
                print(f"Character '{char_name}' not found.")
            return (True, "")

        elif command == "/removecondition":
            try:
                char_name, cond_name = args.split(" ", 1)
            except ValueError:
                print("Usage: /removecondition <character_name> <condition_name>")
                return (True, "")
            char_sheet = self.character_sheets.get(char_name.lower())
            if char_sheet:
                char_sheet.remove_condition(cond_name)
                char_sheet.refresh_cache()
            else:
                print(f"Character '{char_name}' not found.")
            return (True, "")

        elif command == "/worldstate":
            if not args:
                print(json.dumps(self.dm.world_state, indent=2))
            else:
                try:
                    key, value = args.split(" ", 1)
                    self.dm.update_world_state(key, value)
                except ValueError:
                    key = args.strip()
                    print(f"{key}: {self.dm.world_state.get(key)}")
            return (True, "")

        else:
            print(f"Unknown command: {command}")
            return (True, "")

    def _print_attack_breakdown(self, breakdown: dict | None, include_header: bool = True) -> None:
        if not breakdown:
            return

        if include_header:
            print(f"Attacking with {breakdown['weapon_name']}:")

        attack_parts = [f"1d20 + {breakdown['ability_name']} mod ({breakdown['ability_mod']:+})"]
        if breakdown["is_proficient"]:
            attack_parts.append(f"proficiency ({breakdown['proficiency_bonus']:+})")
        if breakdown["poisoned_penalty"]:
            attack_parts.append(f"poisoned penalty ({breakdown['poisoned_penalty']:+})")

        print(f"  To Hit: {' + '.join(attack_parts)} = {breakdown['total_attack_bonus']:+}")

        damage_parts = [breakdown["base_damage_die"]]
        if breakdown["sneak_attack_damage"]:
            damage_parts.append(breakdown["sneak_attack_damage"])
        if breakdown["damage_modifier"]:
            damage_parts.append(f"{breakdown['damage_modifier']:+}")

        print(f"  Damage: {' + '.join(damage_parts)} {breakdown['damage_type']}")

    def _print_spell_breakdown(self, spell_name: str) -> None:
        breakdown = self.player_sheet.get_spellcasting_breakdown(spell_name)
        if not breakdown:
            return

        print(f"Casting {spell_name}:")
        print(
            f"  Spell Attack: 1d20 + {breakdown['ability_name']} mod ({breakdown['ability_mod']:+}) + "
            f"proficiency ({breakdown['proficiency_bonus']:+}) = {breakdown['spell_attack_bonus']:+}"
        )
        print(
            f"  Save DC: 8 + proficiency ({breakdown['proficiency_bonus']}) + "
            f"{breakdown['ability_name']} mod ({breakdown['ability_mod']:+}) = {breakdown['spell_save_dc']}"
        )
        if breakdown["level"] == 0:
            print("  Slot Use: Cantrip, no spell slot spent")
        else:
            print(
                f"  Slot Use: Level {breakdown['level']} slot "
                f"({breakdown['slots_current']}/{breakdown['slots_max']} available before casting)"
            )

    def _print_help(self, topic: str) -> None:
        if not topic:
            print(style("\n--- Help ---", "cyan", bold=True))
            print(style("Topics: commands, combat, spells, exploration", "gray"))
            print(style("Use /help <topic> or /rules <topic> for focused reference.", "gray"))
            print("----------------")
            return

        entries = HELP_TOPICS.get(topic)
        if not entries:
            print(style(f"No help topic named '{topic}'.", "red"))
            print(style(f"Available topics: {', '.join(sorted(HELP_TOPICS))}", "gray"))
            return

        print(style(f"\n--- Help: {topic.title()} ---", "cyan", bold=True))
        for entry in entries:
            print(style(f"- {entry}", "gray"))
        print("-------------------------")

    def _print_rules(self, topic: str) -> None:
        if not topic:
            print(style("Usage: /rules <topic>", "red"))
            print(style(f"Available topics: {', '.join(sorted(RULES_REFERENCE))}", "gray"))
            return

        rule = RULES_REFERENCE.get(topic)
        if not rule:
            print(style(f"No rules entry named '{topic}'.", "red"))
            print(style(f"Available topics: {', '.join(sorted(RULES_REFERENCE))}", "gray"))
            return

        print(style(f"\n--- Rules: {topic.title()} ---", "cyan", bold=True))
        print(style(rule, "gray"))
        print("---------------------------")

    def _print_inventory(self) -> None:
        print("\n--- Your Inventory ---")
        print(f"Gold: {self.player_sheet.gold} gp")
        if not self.player_sheet.inventory_items:
            print("Pack: (Empty)")
            print("----------------------")
            return

        equipped = self.player_sheet.equipped_items or []
        unequipped = self.player_sheet.unequipped_items or []
        print("Equipped:")
        if equipped:
            for item in equipped:
                print(f"- {item}")
        else:
            print("- None")
        print("Pack:")
        if unequipped:
            for item in unequipped:
                print(f"- {item}")
        else:
            print("- Empty")
        print("----------------------")

    def _world_state_list(self, key: str) -> list[str]:
        value = self.dm.world_state.get(key, [])
        if isinstance(value, list):
            return value
        if value:
            return [str(value)]
        return []

    def _record_party_action(self, action: str) -> None:
        actions = self._world_state_list("recent_party_actions")
        actions.append(action)
        self.dm.update_world_state("recent_party_actions", actions[-6:])

    def _print_journal(self) -> None:
        location = self.dm.world_state.get("location", "Unknown")
        objective = self.dm.world_state.get("objective", "No objective recorded yet.")
        quests = self._world_state_list("quests")
        discoveries = self._world_state_list("discoveries")
        npcs = self._world_state_list("notable_npcs")

        print("\n--- Journal ---")
        print(f"Current Location: {location}")
        print(f"Current Objective: {objective}")
        print("Active Quests:")
        if quests:
            for quest in quests:
                print(f"- {quest}")
        else:
            print("- None recorded")
        print("Recent Discoveries:")
        if discoveries:
            for discovery in discoveries:
                print(f"- {discovery}")
        else:
            print("- None recorded")
        print("Notable NPCs:")
        if npcs:
            for npc in npcs:
                print(f"- {npc}")
        else:
            print("- None recorded")
        print("----------------")

    def _print_map(self) -> None:
        location = self.dm.world_state.get("location", "Unknown")
        region = self.dm.world_state.get("region", "Unknown region")
        nearby = self._world_state_list("nearby_locations")
        exits = self._world_state_list("exits")

        print("\n--- Map ---")
        print(f"Region: {region}")
        print(f"Current Location: {location}")
        print("Nearby Locations:")
        if nearby:
            for place in nearby:
                print(f"- {place}")
        else:
            print("- None recorded")
        print("Known Exits:")
        if exits:
            for exit_name in exits:
                print(f"- {exit_name}")
        else:
            print("- None recorded")
        print("-----------")

    def get_suggested_actions(self) -> list[str]:
        suggestions = []
        pending_roll = self.dm.world_state.get("pending_roll")
        if pending_roll:
            suggestions.append("/roll")
            if pending_roll["type"] == "save":
                suggestions.append(f"/roll {pending_roll['ability'].lower()} save")
            else:
                suggestions.append(f"/roll {pending_roll['ability'].lower()}")
        actor = self.current_turn_actor
        if actor["type"] == "companion":
            suggestions.append("/npcturn")
            suggestions.append("/endturn")
            suggestions.append(f"/ask {actor['name'].lower()} What do you want to do?")
            suggestions.append("/turn")
            return suggestions[:4]
        if actor["type"] == "enemy":
            suggestions.append("/enemyturn")
            suggestions.append("/turn")
            suggestions.append("/rules attacks")
            suggestions.append("/sheet")
            return suggestions[:4]

        weapons = [item for item, _ in self.player_sheet.inventory_items if item in WEAPON_DATA]
        known_spells = [spell for spell in self.player_sheet.spells if spell.get("name")]

        if weapons:
            suggestions.append(f"/attack {weapons[0]}")

        if self.player_sheet.class_name == "Rogue" and "Shortsword" in weapons:
            suggestions.append("/attack Shortsword --sneak")

        if known_spells:
            suggestions.append(f"/cast {known_spells[0]['name']}")

        if self.npcs:
            npc_name = next(iter(self.npcs.keys()))
            suggestions.append(f"/ask {npc_name} What do you notice?")

        if self.encounter:
            suggestions.append("/turn")

        suggestions.append("/sheet")
        suggestions.append("look around carefully")
        return suggestions[:4]

    def print_suggested_actions(self) -> None:
        suggestions = self.get_suggested_actions()
        if not suggestions:
            return

        print(style("\nSuggested actions:", "cyan", bold=True))
        for suggestion in suggestions:
            print(f"- {suggestion}")
        if self.teaching_mode:
            print("Teaching: These are starter actions for common D&D turns. You can still type any free-form action you want.")

    def _player_can_act(self) -> bool:
        actor = self.current_turn_actor
        if actor["type"] == "player":
            return True
        print(style(f"It is currently {actor['name']}'s turn, not yours.", "red"))
        self.print_suggested_actions()
        return False

    def player_can_act(self) -> bool:
        return self._player_can_act()

    def _roll_pending_request(self) -> bool:
        pending_roll = self.dm.world_state.get("pending_roll")
        if not pending_roll:
            return False
        self._print_contextual_roll(pending_roll)
        self.dm.update_world_state("pending_roll", None)
        return True

    def _roll_contextual_request(self, raw_args: str) -> bool:
        normalized = raw_args.lower().strip()
        ability_aliases = {
            "str": "STR", "strength": "STR",
            "dex": "DEX", "dexterity": "DEX",
            "con": "CON", "constitution": "CON",
            "int": "INT", "intelligence": "INT",
            "wis": "WIS", "wisdom": "WIS",
            "cha": "CHA", "charisma": "CHA",
        }
        parts = normalized.split()
        if not parts or parts[0] not in ability_aliases:
            return False
        ability = ability_aliases[parts[0]]
        roll_type = "save" if len(parts) > 1 and parts[1] == "save" else "check"
        label = f"{ability} saving throw" if roll_type == "save" else f"{ability} check"
        self._print_contextual_roll({"type": roll_type, "ability": ability, "label": label})
        self.dm.update_world_state("pending_roll", None)
        return True

    def _print_contextual_roll(self, pending_roll: dict) -> None:
        base_roll, explanation = roll_dice("1d20")
        if pending_roll["type"] == "save":
            modifier = self.player_sheet.get_saving_throw_modifier(pending_roll["ability"])
            title = pending_roll.get("label", f"{pending_roll['ability']} saving throw")
        else:
            modifier = self.player_sheet.ability_modifiers.get(pending_roll["ability"], 0)
            title = pending_roll.get("label", f"{pending_roll['ability']} check")
        total = base_roll + modifier
        sign = "+" if modifier >= 0 else "-"
        print(style(f"{title}:", "cyan", bold=True))
        print(f"{explanation} {sign} {abs(modifier)} = {total}")

    def _parse_spell_and_target(self, raw_args: str) -> tuple[str, str]:
        if not raw_args:
            return ("", "")
        normalized = raw_args.strip()
        for spell in sorted((spell["name"] for spell in self.player_sheet.spells if spell.get("name")), key=len, reverse=True):
            if normalized.lower() == spell.lower():
                return (spell, "")
            if normalized.lower().startswith(spell.lower() + " "):
                remainder = normalized[len(spell):].strip()
                if remainder.lower().startswith("at "):
                    remainder = remainder[3:].strip()
                return (spell, remainder)
        return (normalized.title(), "")

    def _auto_start_pending_encounter_for_attack(self) -> None:
        if self.encounter:
            return
        pending = self.dm.world_state.get("pending_encounter_enemies", [])
        if not pending:
            return
        enemies = [{"name": name, "initiative": MONSTER_DATA.get(name, {}).get("initiative", 0)} for name in pending]
        self.dm.update_world_state("pending_encounter_enemies", [])
        print(style("Hostile enemies detected. Starting encounter.", "red", bold=True))
        self._start_encounter(enemies)
        self.print_turn_status()

    def _is_offensive_spell(self, spell_name: str) -> bool:
        spell = SPELL_DATA.get(spell_name)
        if not spell:
            return False
        description = spell.get("description", "").lower()
        offensive_markers = ("damage", "saving throw", "attack", "darts", "hurl", "force sweeps", "pushed")
        return any(marker in description for marker in offensive_markers)

    def get_completion_candidates(self, buffer: str) -> list[str]:
        stripped = buffer.lstrip()
        if not stripped:
            return []

        if stripped.startswith("ask ") or stripped.startswith("/ask "):
            return self._complete_ask(stripped)
        if not stripped.startswith("/"):
            return []

        if " " not in stripped:
            return self._match_prefix(COMMAND_NAMES, stripped)

        command, remainder = stripped.split(" ", 1)
        remainder = remainder.lstrip()
        return self._complete_command_args(command.lower(), remainder)

    def _complete_ask(self, buffer: str) -> list[str]:
        normalized = buffer[1:] if buffer.startswith("/ask ") else buffer
        parts = normalized.split(" ", 2)
        npc_names = sorted(npc.name.lower() for npc in self.npcs.values())
        if len(parts) == 1 or (len(parts) == 2 and not parts[1]):
            prefix = "/ask" if buffer.startswith("/") else "ask"
            return [f"{prefix} {name} " for name in npc_names]
        if len(parts) == 2:
            prefix = parts[1].lower()
            command_prefix = "/ask" if buffer.startswith("/") else "ask"
            return [f"{command_prefix} {name} " for name in npc_names if name.startswith(prefix)]
        return []

    def _complete_command_args(self, command: str, remainder: str) -> list[str]:
        if command in {"/attack", "/equip", "/unequip"}:
            return self._complete_values(command, remainder, [item for item, _ in self.player_sheet.inventory_items])
        if command == "/cast":
            return self._complete_values(command, remainder, [spell["name"] for spell in self.player_sheet.spells if spell.get("name")])
        if command == "/buy":
            return self._complete_values(command, remainder, sorted(STORE_INVENTORY))
        if command == "/help":
            return self._complete_values(command, remainder, sorted(HELP_TOPICS))
        if command == "/rules":
            return self._complete_values(command, remainder, sorted(RULES_REFERENCE))
        if command == "/teach":
            return self._complete_values(command, remainder, ["on", "off", "toggle", "status"])
        if command == "/encounter":
            return self._complete_encounter(remainder)
        if command in {"/addcondition", "/removecondition"}:
            return self._complete_values(command, remainder, sorted(self.character_sheets))
        if command == "/worldstate":
            keys = sorted(str(key) for key in self.dm.world_state)
            return self._complete_values(command, remainder, keys)
        if command == "/roll":
            return self._complete_values(command, remainder, ["1d20", "1d20+5", "2d6+3"])
        return []

    def _complete_encounter(self, remainder: str) -> list[str]:
        parts = remainder.split(" ", 1)
        subcommands = ["start", "status", "end"]
        if not remainder or len(parts) == 1:
            prefix = parts[0] if parts else ""
            matches = self._complete_values("/encounter", prefix, subcommands)
            if prefix.lower() == "start":
                matches.append("/encounter start Goblin")
            return matches
        if parts[0].lower() != "start":
            return []

        enemy_text = parts[1]
        if not enemy_text.strip():
            return ["/encounter start Goblin", "/encounter start Goblin:1", "/encounter start Goblin, Orc:1"]

        entry_prefix = enemy_text.split(",")[-1].strip()
        list_prefix = enemy_text[: len(enemy_text) - len(entry_prefix)]
        if ":" in entry_prefix:
            enemy_name, modifier_prefix = entry_prefix.rsplit(":", 1)
            enemy_name = enemy_name.strip().title()
            modifier_matches = [f"/encounter start {list_prefix}{enemy_name}:{value}" for value in ["-1", "0", "1", "2", "3"] if value.startswith(modifier_prefix)]
            return modifier_matches

        enemy_matches = []
        for enemy_name in ENCOUNTER_ENEMY_SUGGESTIONS:
            if enemy_name.lower().startswith(entry_prefix.lower()):
                enemy_matches.append(f"/encounter start {list_prefix}{enemy_name}")
                enemy_matches.append(f"/encounter start {list_prefix}{enemy_name}:1")
        return enemy_matches
        

    def _complete_values(self, command: str, remainder: str, values: list[str]) -> list[str]:
        prefix = remainder.lower()
        matches = []
        for value in values:
            if value.lower().startswith(prefix):
                suffix = "" if command in {"/encounter", "/roll"} else ""
                matches.append(f"{command} {value}{suffix}".rstrip() if prefix else f"{command} {value}")
        return matches

    def _match_prefix(self, values: list[str], prefix: str) -> list[str]:
        lowered_prefix = prefix.lower()
        return [value for value in values if value.startswith(lowered_prefix)]

    @property
    def current_actor_name(self) -> str:
        return self.current_turn_actor["name"]

    @property
    def current_turn_actor(self) -> dict:
        if self.encounter and self.encounter["order"]:
            return self.encounter["order"][self.encounter["index"]]
        if not self.turn_order:
            return {"name": self.player_sheet.name, "type": "player"}
        return {"name": self.turn_order[self.turn_index], "type": "player" if self.turn_order[self.turn_index] == self.player_sheet.name else "companion"}

    def advance_turn(self) -> str:
        if self.encounter and self.encounter["order"]:
            previous_index = self.encounter["index"]
            self.encounter["index"] = (self.encounter["index"] + 1) % len(self.encounter["order"])
            if self.encounter["index"] == 0 and previous_index != 0:
                self.encounter["round"] += 1
            return self.current_actor_name
        if not self.turn_order:
            return self.player_sheet.name
        previous_index = self.turn_index
        self.turn_index = (self.turn_index + 1) % len(self.turn_order)
        if self.turn_index == 0 and previous_index != 0:
            self.round_number += 1
            self._sync_story_pacing()
        return self.current_actor_name

    def _sync_story_pacing(self) -> None:
        target_rounds = int(self.dm.world_state.get("target_rounds", 0) or 0)
        self.dm.update_world_state("current_round", self.round_number)
        if target_rounds > 0:
            remaining_rounds = max(target_rounds - self.round_number, 0)
            self.dm.update_world_state("remaining_rounds", remaining_rounds)
            progress_ratio = self.round_number / target_rounds
            if progress_ratio <= 0.25:
                story_phase = "opening"
            elif progress_ratio <= 0.70:
                story_phase = "midgame"
            elif progress_ratio <= 0.90:
                story_phase = "climax"
            else:
                story_phase = "resolution"
            self.dm.update_world_state("story_phase", story_phase)

    def print_turn_status(self) -> None:
        if self.encounter:
            print(style("\n--- Encounter Order ---", "cyan", bold=True))
            print(f"Round: {self.encounter['round']}")
            print(f"Active Turn: {style(self.current_actor_name, 'gold', bold=True)}")
            print("Order:")
            for actor in self.encounter["order"]:
                marker = "->" if actor["name"] == self.current_actor_name else "  "
                print(f"{marker} {style(actor['name'], 'gold', bold=actor['name'] == self.current_actor_name)} [{actor['type']}] ({actor['total']})")
            print("-----------------------")
            return

        print(style("\n--- Turn Order ---", "cyan", bold=True))
        print(f"Round: {self.round_number}")
        print(f"Active Turn: {style(self.current_actor_name, 'gold', bold=True)}")
        print("Order:")
        for name in self.turn_order:
            marker = "->" if name == self.current_actor_name else "  "
            print(f"{marker} {style(name, 'gold', bold=name == self.current_actor_name)}")
        print("------------------")

    def _handle_encounter(self, args: str) -> tuple[bool, str]:
        if not args:
            enemies = self._resolve_encounter_enemies()
            if not enemies:
                print(style("Encounter setup cancelled.", "red"))
                return (True, "")
            self._start_encounter(enemies)
            self.print_turn_status()
            return (True, "")

        parts = args.split(" ", 1)
        subcommand = parts[0].lower()
        remainder = parts[1] if len(parts) > 1 else ""

        if subcommand == "start":
            enemies = self._parse_enemy_entries(remainder) if remainder else self._resolve_encounter_enemies()
            if not enemies:
                print(style("Encounter setup cancelled.", "red"))
                return (True, "")
            self._start_encounter(enemies)
            self.print_turn_status()
            return (True, "")

        if subcommand == "status":
            if not self.encounter:
                print(style("No active encounter.", "red"))
                return (True, "")
            self.print_turn_status()
            return (True, "")

        if subcommand == "end":
            self.encounter = None
            self.dm.update_world_state("encounter_enemies", "")
            print(style("Encounter ended.", "green", bold=True))
            self.print_turn_status()
            return (True, "")

        print(style("Usage: /encounter <start|status|end> [enemies]", "red"))
        return (True, "")

    def _resolve_encounter_enemies(self) -> list[dict]:
        pending = self.dm.world_state.get("pending_encounter_enemies", [])
        if pending:
            counts = Counter(pending)
            summary = ", ".join(f"{name} x{count}" if count > 1 else name for name, count in counts.items())
            confirmation = input(f"Use detected enemies ({summary})? [Y/n] ").strip().lower()
            if confirmation in ("", "y", "yes"):
                enemies = [{"name": name, "initiative": MONSTER_DATA.get(name, {}).get("initiative", 0)} for name in pending]
                self.dm.update_world_state("pending_encounter_enemies", [])
                return enemies
        return self._prompt_for_encounter_enemies()

    def _prompt_for_encounter_enemies(self) -> list[dict]:
        print(style("\nEncounter setup", "cyan", bold=True))
        print(style("Enter enemy names one at a time. Press Enter on a blank line when finished.", "gray"))
        print(style(f"Suggestions: {', '.join(ENCOUNTER_ENEMY_SUGGESTIONS)}", "gray"))

        enemies = []
        while True:
            enemy_name = input("Enemy name > ").strip()
            if not enemy_name:
                break

            initiative_raw = input("Initiative modifier [0] > ").strip()
            try:
                initiative_mod = int(initiative_raw) if initiative_raw else 0
            except ValueError:
                print(style("Initiative modifier must be a whole number. Using 0.", "red"))
                initiative_mod = 0

            enemies.append({"name": enemy_name.title(), "initiative": initiative_mod})

        return enemies

    def _prompt_for_ask(self) -> str:
        if not self.npcs:
            return ""

        print(style("\nConversation setup", "cyan", bold=True))
        companion_names = [npc.name for npc in self.npcs.values()]
        print(style(f"Companions: {', '.join(companion_names)}", "gray"))

        npc_name = input("Companion name > ").strip()
        if not npc_name:
            return ""

        message = input("Question > ").strip()
        if not message:
            return ""

        return f"ask {npc_name} {message}"

    def _parse_enemy_entries(self, raw: str) -> list[dict]:
        enemies = []
        for entry in raw.split(","):
            token = entry.strip()
            if not token:
                continue
            if ":" in token:
                name, modifier = token.rsplit(":", 1)
                try:
                    initiative_mod = int(modifier.strip())
                except ValueError:
                    initiative_mod = 0
                enemy_name = name.strip().title()
            else:
                enemy_name = token.title()
                initiative_mod = 0
            enemies.append({"name": enemy_name, "initiative": initiative_mod})
        return enemies

    def _start_encounter(self, enemies: list[dict]) -> None:
        order = [self._build_actor_entry(self.player_sheet.name, "player", getattr(self.player_sheet, "initiative", 0))]
        for npc in self.npcs.values():
            npc_sheet = self.character_sheets.get(npc.name.lower())
            modifier = getattr(npc_sheet, "initiative", 0) if npc_sheet else 0
            order.append(self._build_actor_entry(npc.name, "companion", modifier))
        for enemy in enemies:
            order.append(self._build_actor_entry(enemy["name"], "enemy", enemy["initiative"]))

        order.sort(key=lambda actor: (-actor["total"], -actor["roll"], actor["name"]))
        self.encounter = {"order": order, "index": 0, "round": 1}
        enemy_names = ", ".join(enemy["name"] for enemy in enemies)
        self.dm.world_state["encounter_enemies"] = enemy_names
        self.dm.update_world_state("encounter_enemies", enemy_names)
        print(style(f"Encounter started against: {enemy_names}.", "green", bold=True))

    def _build_actor_entry(self, name: str, actor_type: str, initiative_modifier: int) -> dict:
        roll, explanation = roll_dice("1d20")
        total = roll + initiative_modifier
        print(f"Initiative for {name}: {explanation} + {initiative_modifier} = {total}")
        return {
            "name": name,
            "type": actor_type,
            "modifier": initiative_modifier,
            "roll": roll,
            "total": total,
        }
