# dnd/cli/__init__.py
import json
from dnd.data import HELP_TOPICS, RULES_REFERENCE, STORE_INVENTORY, WEAPON_DATA
from dnd.game import roll_dice
from dnd.database import get_db_connection
from dnd.ui import speaker, style


class CommandHandler:
    def __init__(self, player_sheet, character_sheets, npcs, dm):
        self.player_sheet = player_sheet
        self.character_sheets = character_sheets
        self.npcs = npcs
        self.dm = dm
        self.teaching_mode = False
        self.turn_order = [self.player_sheet.name] + [npc.name for npc in self.npcs.values()]
        self.turn_index = 0
        self.round_number = 1
        self.encounter = None

    def handle(self, user_input: str) -> tuple[bool, str]:
        if user_input.lower().startswith("ask "):
            return self._handle_ask(user_input)
        return self._handle_command(user_input)

    def _handle_ask(self, user_input: str) -> tuple[bool, str]:
        parts = user_input.split(" ", 2)
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
        else:
            print(style(f"You don't have a companion named {npc_name}.", "red"))
        return (True, "")

    def _handle_command(self, user_input: str) -> tuple[bool, str]:
        parts = user_input.split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "/roll":
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
            is_sneak_attack = "--sneak" in args
            weapon_name = args.replace("--sneak", "").strip().title()
            if not weapon_name:
                print(style("Usage: /attack <weapon name> [--sneak]", "red"))
            elif weapon_name in [item for item, _ in self.player_sheet.inventory_items]:
                breakdown = self.player_sheet.get_attack_breakdown(weapon_name, is_sneak_attack)
                self._print_attack_breakdown(breakdown)
                if self.teaching_mode and breakdown:
                    print("Teaching: Roll the d20 and add the total to-hit bonus. If that meets or beats the target's AC, roll the listed damage.")
            else:
                print(style(f"You do not have a '{weapon_name}' in your inventory.", "red"))
            return (True, "")

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
            spell_name = args.strip().title()
            known_spell = next((s for s in self.player_sheet.spells if s['name'].title() == spell_name), None)
            if not spell_name:
                print(style("Usage: /cast <spell name>", "red"))
                return (True, "")
            elif known_spell:
                self._print_spell_breakdown(spell_name)
                if self.teaching_mode:
                    if known_spell["level"] == 0:
                        print("Teaching: Cantrips can be cast freely. Use the spell attack bonus if the spell asks for an attack roll, or the save DC if the target rolls a save.")
                    else:
                        print("Teaching: Leveled spells spend a spell slot. The save DC is what enemies try to beat on saving throws; the spell attack bonus is what you add to attack-roll spells.")
                if self.player_sheet.cast_spell(known_spell['level'], known_spell['name']):
                    print(style(f"You cast {spell_name}.", "green", bold=True))
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
            print(f"\n{speaker(npc.name, 'magenta')} ", end="")
            response = npc.generate_turn_action(self.dm.history, scene_summary)
            if response:
                print(response)
                self.dm.add_history("assistant", f"{npc.name}: {response}")
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
        actor = self.current_turn_actor
        if actor["type"] == "companion":
            suggestions.append("/npcturn")
            suggestions.append("/endturn")
            suggestions.append(f"ask {actor['name'].lower()} What do you want to do?")
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

        if self.encounter:
            suggestions.append("/turn")

        if self.npcs:
            npc_name = next(iter(self.npcs.keys()))
            suggestions.append(f"ask {npc_name} What do you notice?")

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
        return self.current_actor_name

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
            print(style("Usage: /encounter <start|status|end> [enemies]", "red"))
            return (True, "")

        parts = args.split(" ", 1)
        subcommand = parts[0].lower()
        remainder = parts[1] if len(parts) > 1 else ""

        if subcommand == "start":
            if not remainder:
                print(style("Usage: /encounter start Goblin, Orc:1, Wolf:2", "red"))
                return (True, "")
            enemies = self._parse_enemy_entries(remainder)
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
