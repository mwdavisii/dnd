# dnd/cli/__init__.py
import json
from dnd.data import STORE_INVENTORY
from dnd.game import roll_dice
from dnd.database import get_db_connection


class CommandHandler:
    def __init__(self, player_sheet, character_sheets, npcs, dm):
        self.player_sheet = player_sheet
        self.character_sheets = character_sheets
        self.npcs = npcs
        self.dm = dm

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
            print(f"\n{self.npcs[npc_name].name}: ", end='')
            self.npcs[npc_name].generate_response(message, self.dm.history)
        else:
            print(f"You don't have a companion named {npc_name}.")
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
                print(e)
            return (True, "")

        elif command == "/sheet":
            self.player_sheet.refresh_cache()
            print(self.player_sheet)
            return (True, "")

        elif command == "/testhp":
            try:
                self.player_sheet.update_hp(int(args))
            except (ValueError, IndexError):
                print("Usage: /testhp <amount>")
            return (True, "")

        elif command == "/attack":
            is_sneak_attack = "--sneak" in args
            weapon_name = args.replace("--sneak", "").strip().title()
            if not weapon_name:
                print("Usage: /attack <weapon name> [--sneak]")
            elif weapon_name in [item for item, _ in self.player_sheet.inventory_items]:
                bonus = self.player_sheet.get_attack_bonus(weapon_name)
                damage = self.player_sheet.get_damage_roll(weapon_name, is_sneak_attack)
                print(f"Attacking with {weapon_name}:")
                print(f"  Attack Bonus: 1d20 + {bonus}")
                print(f"  Damage: {damage}")
            else:
                print(f"You do not have a '{weapon_name}' in your inventory.")
            return (True, "")

        elif command == "/sneakattack":
            weapon_name = "Shortsword"
            if self.player_sheet.class_name == "Rogue" and weapon_name in [item for item, _ in self.player_sheet.inventory_items]:
                bonus = self.player_sheet.get_attack_bonus(weapon_name)
                damage = self.player_sheet.get_damage_roll(weapon_name, is_sneak_attack=True)
                print(f"Performing a Sneak Attack with {weapon_name}:")
                print(f"  Attack Bonus: 1d20 + {bonus}")
                print(f"  Damage: {damage}")
            else:
                print("You can't perform a sneak attack.")
            return (True, "")

        elif command == "/cast":
            spell_name = args.strip().title()
            known_spell = next((s for s in self.player_sheet.spells if s['name'].title() == spell_name), None)
            if not spell_name:
                print("Usage: /cast <spell name>")
                return (True, "")
            elif known_spell:
                if self.player_sheet.cast_spell(known_spell['level'], known_spell['name']):
                    print(f"You cast {spell_name}.")
                    return (False, f"I cast the {spell_name} spell.")
                else:
                    print(f"You don't have any level {known_spell['level']} spell slots left.")
                    return (True, "")
            else:
                print(f"You don't know the spell '{spell_name}'.")
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
                print("Usage: /buy <item name>")
            elif item_data:
                cost = item_data['cost']
                if self.player_sheet.spend_gold(cost):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO inventory (character_id, item_name, quantity) VALUES (?, ?, ?)", (self.player_sheet._id, item_name, 1))
                    conn.commit()
                    conn.close()
                    self.player_sheet.refresh_cache()
                    print(f"You bought a {item_name}!")
            else:
                print(f"'{item_name}' is not available in the shop.")
            return (True, "")

        elif command == "/shortrest":
            if not args:
                print("Usage: /shortrest <number of Hit Dice to spend>")
                return (True, "")
            try:
                num_dice = int(args)
                self.player_sheet.take_short_rest(num_dice)
                return (False, f"I take a short rest, spending {num_dice} Hit Dice.")
            except ValueError:
                print("Invalid number of Hit Dice.")
                return (True, "")

        elif command == "/longrest":
            self.player_sheet.take_long_rest()
            return (False, "I take a long rest.")

        elif command == "/rage":
            if self.player_sheet.class_name == "Barbarian":
                self.player_sheet.start_rage()
            else:
                print("Only Barbarians can rage.")
            return (True, "")

        elif command == "/unrage":
            if self.player_sheet.class_name == "Barbarian":
                self.player_sheet.end_rage()
            else:
                print("Only Barbarians can be raging.")
            return (True, "")

        elif command == "/inventory":
            self.player_sheet.refresh_cache()
            print("\n--- Your Inventory ---")
            if not self.player_sheet.inventory_items:
                print("  (Empty)")
            else:
                print("Equipped:")
                for item in self.player_sheet.equipped_items:
                    print(f"- {item}")
                print("Unequipped:")
                for item in self.player_sheet.unequipped_items:
                    print(f"- {item}")
            print("----------------------")
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
