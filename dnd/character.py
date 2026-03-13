# dnd/character.py
import json
import math
import random # Needed for rolling hit dice
from .database import get_db_connection
from .data import WEAPON_DATA, SKILL_TO_ABILITY_MAP, ARMOR_DATA, CLASS_DATA, SPELL_DATA
from .game import roll_dice # Import roll_dice function

class CharacterSheet:
    def __init__(self, name: str):
        self._name = name
        self._id = self._get_id()
        self.refresh_cache()

    def refresh_cache(self):
        self._proficiencies_cache = self._fetch_proficiencies()
        self._inventory_cache = self._fetch_inventory()
        self._spells_cache = self._fetch_spells()
        self._conditions_cache = self._fetch_conditions()

    def _fetch_proficiencies(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT p.name FROM proficiencies p JOIN character_proficiencies cp ON p.id = cp.proficiency_id WHERE cp.character_id = ?", (self._id,)).fetchall()
        conn.close()
        return [row['name'] for row in rows]

    def _fetch_inventory(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT item_name, equipped FROM inventory WHERE character_id = ?", (self._id,)).fetchall()
        conn.close()
        return [(row['item_name'], bool(row['equipped'])) for row in rows] # Now returns (name, equipped_status)

    def _fetch_spells(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT s.* FROM spells s JOIN character_spells cs ON s.id = cs.spell_id WHERE cs.character_id = ?", (self._id,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def _fetch_conditions(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT condition_name, duration_turns FROM conditions WHERE character_id = ?", (self._id,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def _get_character_row(self):
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM characters WHERE name = ?", (self.name,)).fetchone()
        conn.close()
        return row

    def _get_id(self):
        conn = get_db_connection()
        char_data = conn.execute("SELECT id FROM characters WHERE name = ?", (self._name,)).fetchone()
        conn.close()
        if not char_data: raise ValueError(f"Character '{self._name}' not found.")
        return char_data['id']

    def _get_modifier_from_score(self, score):
        return math.floor((score - 10) / 2)

    @property
    def name(self): return self._name
    @property
    def class_name(self): return self._get_character_row()['class_name']
    @property
    def sex(self): return self._get_character_row()['sex']
    @property
    def pronouns(self): return self._get_character_row()['pronouns']
    @property
    def stats(self): return json.loads(self._get_character_row()['stats'])
    @property
    def current_hp(self): return self._get_character_row()['hp_current']
    @property
    def max_hp(self): return self._get_character_row()['hp_max']
    @property
    def level(self): return self._get_character_row()['level']
    @property
    def proficiency_bonus(self): return self._get_character_row()['proficiency_bonus']
    @property
    def hit_die_type(self): return self._get_character_row()['hit_die_type']
    @property
    def hit_dice_current(self): return self._get_character_row()['hit_dice_current']
    @property
    def hit_dice_max(self): return self._get_character_row()['hit_dice_max']
    @property
    def gold(self): return self._get_character_row()['gold']
    
    @property
    def is_concentrating(self): return self._get_character_row()['is_concentrating']

    @property
    def is_raging(self): return self._get_character_row()['is_raging']

    def start_rage(self):
        """Starts the character's rage."""
        if self.class_name == "Barbarian":
            conn = get_db_connection()
            conn.execute("UPDATE characters SET is_raging = 1 WHERE id = ?", (self._id,))
            conn.commit()
            conn.close()
            self.refresh_cache()
            print(f"[{self.name} is now raging!]")
        else:
            print(f"[{self.name} is not a Barbarian and cannot rage.]")

    def end_rage(self):
        """Ends the character's rage."""
        conn = get_db_connection()
        conn.execute("UPDATE characters SET is_raging = 0 WHERE id = ?", (self._id,))
        conn.commit()
        conn.close()
        self.refresh_cache()
        print(f"[{self.name} is no longer raging.]")

    def break_concentration(self):
        """Breaks the character's concentration."""
        conn = get_db_connection()
        conn.execute("UPDATE characters SET is_concentrating = 0 WHERE id = ?", (self._id,))
        conn.commit()
        conn.close()
        self.refresh_cache()
        print(f"[{self.name} loses concentration.]")
    
    @property
    def inventory_items(self): # Returns a list of (item_name, equipped_status)
        return self._inventory_cache
    
    @property
    def equipped_items(self):
        return [item_name for item_name, equipped in self.inventory_items if equipped]

    @property
    def unequipped_items(self):
        return [item_name for item_name, equipped in self.inventory_items if not equipped]

    @property
    def proficiencies(self): return self._proficiencies_cache
    
    @property
    def spells(self): return self._spells_cache

    @property
    def conditions(self): return self._conditions_cache

    def add_condition(self, condition_name: str, duration_turns: int = -1):
        """Adds a condition to the character."""
        conn = get_db_connection()
        conn.execute("INSERT INTO conditions (character_id, condition_name, duration_turns) VALUES (?, ?, ?)",
                     (self._id, condition_name, duration_turns))
        conn.commit()
        conn.close()
        self.refresh_cache()
        print(f"[{self.name} is now {condition_name}.]")

    def remove_condition(self, condition_name: str):
        """Removes a condition from the character."""
        conn = get_db_connection()
        conn.execute("DELETE FROM conditions WHERE character_id = ? AND condition_name = ?", (self._id, condition_name))
        conn.commit()
        conn.close()
        self.refresh_cache()
        print(f"[{self.name} is no longer {condition_name}.]")

    def has_condition(self, condition_name: str) -> bool:
        """Checks if the character has a specific condition."""
        return any(c['condition_name'] == condition_name for c in self.conditions)

    @property
    def spell_slots(self):
        row = self._get_character_row()
        return {i: {'current': row[f'spell_slots_l{i}_current'], 'max': row[f'spell_slots_l{i}_max']} for i in range(1, 4)}

    @property
    def spellcasting_ability(self):
        return CLASS_DATA.get(self.class_name, {}).get('spellcasting_ability')
    @property
    def spellcasting_ability_modifier(self):
        ability = self.spellcasting_ability
        return self.ability_modifiers.get(ability, 0) if ability else 0
    @property
    def spell_save_dc(self):
        if not self.spellcasting_ability: return None
        return 8 + self.proficiency_bonus + self.spellcasting_ability_modifier
    @property
    def spell_attack_bonus(self):
        if not self.spellcasting_ability: return None
        return self.proficiency_bonus + self.spellcasting_ability_modifier
    @property
    def ability_modifiers(self):
        return {stat: self._get_modifier_from_score(score) for stat, score in self.stats.items()}
    @property
    def initiative(self): return self.ability_modifiers.get("DEX", 0)
    @property
    def armor_class(self):
        dex_mod = self.ability_modifiers.get("DEX", 0)
        ac = 10 + dex_mod
        
        equipped_armor = None
        for item_name in self.equipped_items: # Check equipped items
            if item_name in ARMOR_DATA and ARMOR_DATA[item_name]['type'] != 'shield':
                equipped_armor = ARMOR_DATA[item_name]
                break
        
        if equipped_armor:
            if equipped_armor['type'] == 'light': ac = equipped_armor['ac'] + dex_mod
            elif equipped_armor['type'] == 'medium': ac = equipped_armor['ac'] + min(dex_mod, equipped_armor.get('dex_cap', 2))
            elif equipped_armor['type'] == 'heavy': ac = equipped_armor['ac']
        
        if "Shield" in self.equipped_items: # Check equipped items
            ac += ARMOR_DATA["Shield"]["ac"]
        return ac

    @property
    def passive_perception(self): return 10 + self.get_skill_modifier("Perception")

    def get_saving_throw_modifier(self, ability_name: str):
        mod = self.ability_modifiers.get(ability_name.upper(), 0)
        if f"{ability_name.title()} Saving Throw" in self.proficiencies: mod += self.proficiency_bonus

        if self.is_raging and ability_name.upper() == "STR":
            # NOTE: This is a simplification. True advantage would mean rolling twice and taking the higher result.
            mod += 5
            
        return mod

    def get_skill_modifier(self, skill_name: str):
        ability = SKILL_TO_ABILITY_MAP.get(skill_name.title())
        if not ability: return 0
        mod = self.ability_modifiers.get(ability, 0)
        if skill_name.title() in self.proficiencies: mod += self.proficiency_bonus
        
        # Apply disadvantage for being poisoned
        if self.has_condition("Poisoned"):
            # NOTE: This is a simplification. True disadvantage would mean rolling twice and taking the lower result.
            # This would require changes to the roll_dice function.
            mod -= 5
            
        return mod

    def get_attack_bonus(self, weapon_name: str):
        weapon_info = WEAPON_DATA.get(weapon_name)
        if not weapon_info: return 0
        mods = self.ability_modifiers
        ability_mod = mods.get("DEX", 0) if any(p in weapon_info.get("properties", []) for p in ["Ranged", "Thrown"]) else mods.get("STR", 0)
        if "Finesse" in weapon_info["properties"]: ability_mod = max(mods.get("STR", 0), mods.get("DEX", 0))
        is_proficient = any(p in self.proficiencies for p in [weapon_name, "Simple Weapons", "Martial Weapons"])
        
        bonus = ability_mod + self.proficiency_bonus if is_proficient else ability_mod
        
        # Apply disadvantage for being poisoned
        if self.has_condition("Poisoned"):
            # NOTE: This is a simplification. True disadvantage would mean rolling twice and taking the lower result.
            # This would require changes to the roll_dice function.
            bonus -= 5
            
        return bonus

    def get_attack_breakdown(self, weapon_name: str, is_sneak_attack: bool = False) -> dict | None:
        weapon_info = WEAPON_DATA.get(weapon_name)
        if not weapon_info:
            return None

        properties = weapon_info.get("properties", [])
        mods = self.ability_modifiers
        ability_name = "DEX" if any(p in properties for p in ["Ranged", "Thrown"]) else "STR"
        if "Finesse" in properties:
            ability_name = "DEX" if mods.get("DEX", 0) >= mods.get("STR", 0) else "STR"

        ability_mod = mods.get(ability_name, 0)
        proficient_sources = [weapon_name, "Simple Weapons", "Martial Weapons"]
        is_proficient = any(p in self.proficiencies for p in proficient_sources)
        proficiency_bonus = self.proficiency_bonus if is_proficient else 0
        poisoned_penalty = -5 if self.has_condition("Poisoned") else 0
        total_attack_bonus = ability_mod + proficiency_bonus + poisoned_penalty

        sneak_attack_damage = "1d6" if is_sneak_attack and self.class_name == "Rogue" else None
        rage_damage = 2 if self.is_raging and self.class_name == "Barbarian" and "Ranged" not in properties else 0

        return {
            "weapon_name": weapon_name,
            "ability_name": ability_name,
            "ability_mod": ability_mod,
            "is_proficient": is_proficient,
            "proficiency_bonus": proficiency_bonus,
            "poisoned_penalty": poisoned_penalty,
            "total_attack_bonus": total_attack_bonus,
            "base_damage_die": weapon_info["damage"],
            "damage_type": weapon_info["type"],
            "damage_modifier": ability_mod + rage_damage,
            "rage_damage": rage_damage,
            "sneak_attack_damage": sneak_attack_damage,
        }

    def get_damage_roll(self, weapon_name: str, is_sneak_attack: bool = False):
        weapon_info = WEAPON_DATA.get(weapon_name)
        if not weapon_info: return "N/A"
        mods = self.ability_modifiers
        ability_mod = mods.get("DEX", 0) if any(p in weapon_info.get("properties", []) for p in ["Ranged", "Thrown"]) else mods.get("STR", 0)
        if "Finesse" in weapon_info["properties"]: ability_mod = max(mods.get("STR", 0), mods.get("DEX", 0))
        damage_die, damage_type = weapon_info['damage'], weapon_info['type']
        
        sneak_attack_damage = ""
        if is_sneak_attack and self.class_name == "Rogue":
            sneak_attack_damage = " + 1d6"

        rage_damage = 0
        if self.is_raging and self.class_name == "Barbarian" and "Ranged" not in weapon_info.get("properties", []):
            rage_damage = 2
            
        return f"{damage_die}{sneak_attack_damage} {ability_mod + rage_damage:+} {damage_type}" if (ability_mod + rage_damage) != 0 else f"{damage_die}{sneak_attack_damage} {damage_type}"

    def get_spellcasting_breakdown(self, spell_name: str) -> dict | None:
        spell_info = SPELL_DATA.get(spell_name)
        if not spell_info or not self.spellcasting_ability:
            return None

        slots = self.spell_slots.get(spell_info["level"]) if spell_info["level"] > 0 else None
        return {
            "spell_name": spell_name,
            "level": spell_info["level"],
            "ability_name": self.spellcasting_ability,
            "ability_mod": self.spellcasting_ability_modifier,
            "proficiency_bonus": self.proficiency_bonus,
            "spell_save_dc": self.spell_save_dc,
            "spell_attack_bonus": self.spell_attack_bonus,
            "range": spell_info.get("range"),
            "casting_time": spell_info.get("casting_time"),
            "duration": spell_info.get("duration"),
            "slots_current": slots["current"] if slots else None,
            "slots_max": slots["max"] if slots else None,
        }

    def resolve_attack(self, weapon_name: str, target_ac: int, is_sneak_attack: bool = False) -> dict | None:
        breakdown = self.get_attack_breakdown(weapon_name, is_sneak_attack)
        if not breakdown:
            return None

        attack_roll, _ = roll_dice("1d20")
        total_to_hit = attack_roll + breakdown["total_attack_bonus"]
        is_critical = attack_roll == 20
        is_hit = is_critical or (attack_roll != 1 and total_to_hit >= target_ac)

        result = {
            "weapon_name": weapon_name,
            "target_ac": target_ac,
            "attack_roll": attack_roll,
            "to_hit_bonus": breakdown["total_attack_bonus"],
            "total_to_hit": total_to_hit,
            "is_hit": is_hit,
            "is_critical": is_critical,
            "damage_total": 0,
            "damage_breakdown": [],
            "damage_type": breakdown["damage_type"],
        }

        if not is_hit:
            return result

        damage_parts = [breakdown["base_damage_die"]]
        if breakdown["sneak_attack_damage"]:
            damage_parts.append(breakdown["sneak_attack_damage"])

        damage_total = 0
        damage_breakdown = []
        for damage_part in damage_parts:
            dice_count, die_type = damage_part.lower().split("d")
            if is_critical:
                damage_part = f"{int(dice_count) * 2}d{die_type}"
            part_total, _ = roll_dice(damage_part)
            damage_total += part_total
            damage_breakdown.append({"source": damage_part, "total": part_total})

        damage_total += breakdown["damage_modifier"]
        result["damage_total"] = max(0, damage_total)
        result["damage_breakdown"] = damage_breakdown
        result["damage_modifier"] = breakdown["damage_modifier"]
        return result

    def update_hp(self, amount: int, damage_type: str = None):
        if self.is_raging and amount < 0 and damage_type in ["bludgeoning", "piercing", "slashing"]:
            amount //= 2

        if amount < 0 and self.is_concentrating:
            damage = abs(amount)
            dc = max(10, damage // 2)
            con_save = self.get_saving_throw_modifier("CON")
            roll, _ = roll_dice("d20")
            if roll + con_save < dc:
                self.break_concentration()
        
        new_hp = min(self.current_hp + amount, self.max_hp)
        new_hp = max(0, new_hp)
        conn = get_db_connection()
        conn.execute("UPDATE characters SET hp_current = ? WHERE id = ?", (new_hp, self._id))
        conn.commit()
        conn.close()

    def take_short_rest(self, num_hit_dice_to_spend: int):
        if num_hit_dice_to_spend <= 0:
            print("[You decide not to spend any Hit Dice.]")
            return
        if self.hit_dice_current == 0:
            print("[You have no Hit Dice left to spend.]")
            return

        conn = get_db_connection()
        total_healing = 0
        hit_dice_spent = 0
        con_mod = self.ability_modifiers.get("CON", 0)
        
        for _ in range(min(num_hit_dice_to_spend, self.hit_dice_current)):
            # Assuming hit_die_type is 'd6', 'd8', etc.
            roll_result, _ = roll_dice("1" + self.hit_die_type) 
            healing = roll_result + con_mod
            total_healing += healing
            hit_dice_spent += 1

        new_hp = min(self.current_hp + total_healing, self.max_hp)
        new_hit_dice_current = self.hit_dice_current - hit_dice_spent

        conn.execute("UPDATE characters SET hp_current = ?, hit_dice_current = ? WHERE id = ?", (new_hp, new_hit_dice_current, self._id))
        conn.commit()
        conn.close()
        self.refresh_cache()
        print(f"[{self.name} spent {hit_dice_spent} Hit Dice and regained {total_healing} HP. Current HP: {self.current_hp}/{self.max_hp}]")
    
    def take_long_rest(self):
        conn = get_db_connection()
        # Restore HP to max
        new_hp = self.max_hp
        # Restore Hit Dice to max (up to level)
        new_hit_dice_current = self.level
        # Break concentration
        self.break_concentration()
        # Restore spell slots
        for i in range(1, 4): # Assuming L1, L2, L3 spell slots max
            conn.execute(f"UPDATE characters SET spell_slots_l{i}_current = spell_slots_l{i}_max WHERE id = ?", (self._id,))
        
        conn.execute("UPDATE characters SET hp_current = ?, hit_dice_current = ?, spell_slots_l1_current = spell_slots_l1_max, spell_slots_l2_current = spell_slots_l2_max, spell_slots_l3_current = spell_slots_l3_max WHERE id = ?", (new_hp, new_hit_dice_current, self._id))
        conn.commit()
        conn.close()
        self.refresh_cache()
        print(f"[{self.name} finished a Long Rest. HP restored, Hit Dice and Spell Slots regained.]")

    def level_up(self, new_max_hp_increase: int = 5): # Added parameter for flexibility
        new_level = self.level + 1
        new_max_hp = self.max_hp + new_max_hp_increase
        new_prof_bonus = self.proficiency_bonus
        if new_level in [5, 9, 13, 17]:
            new_prof_bonus += 1
        conn = get_db_connection()
        conn.execute("UPDATE characters SET level = ?, hp_max = ?, hp_current = ?, proficiency_bonus = ?, hit_dice_max = ? WHERE id = ?", (new_level, new_max_hp, new_max_hp, new_prof_bonus, new_level, self._id))
        conn.commit()
        conn.close()
        self.refresh_cache()
        print(f"[{self.name} has reached level {new_level}! Max HP is now {new_max_hp}.]")


    def add_gold(self, amount: int):
        conn = get_db_connection()
        current_gold = self.gold
        new_gold = current_gold + amount
        conn.execute("UPDATE characters SET gold = ? WHERE id = ?", (new_gold, self._id))
        conn.commit()
        conn.close()
        print(f"[{self.name} gained {amount} gold. Total: {new_gold} gp]")
        self.refresh_cache()

    def spend_gold(self, amount: int) -> bool:
        conn = get_db_connection()
        current_gold = self.gold
        if current_gold >= amount:
            new_gold = current_gold - amount
            conn.execute("UPDATE characters SET gold = ? WHERE id = ?", (new_gold, self._id))
            conn.commit()
            conn.close()
            print(f"[{self.name} spent {amount} gold. Total: {new_gold} gp]")
            self.refresh_cache()
            return True
        else:
            print(f"[{self.name} does not have enough gold to spend {amount} (current: {current_gold} gp)]")
            conn.close()
            return False

    def equip_item(self, item_name: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM inventory WHERE character_id = ? AND item_name = ?", (self._id, item_name))
        item_row = cursor.fetchone()
        if item_row:
            cursor.execute("UPDATE inventory SET equipped = 1 WHERE id = ?", (item_row['id'],))
            conn.commit()
            conn.close()
            self.refresh_cache()
            print(f"[{self.name} equipped {item_name}.]")
            return True
        conn.close()
        print(f"[{self.name} does not have {item_name} to equip.]")
        return False

    def unequip_item(self, item_name: str) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM inventory WHERE character_id = ? AND item_name = ?", (self._id, item_name))
        item_row = cursor.fetchone()
        if item_row:
            cursor.execute("UPDATE inventory SET equipped = 0 WHERE id = ?", (item_row['id'],))
            conn.commit()
            conn.close()
            self.refresh_cache()
            print(f"[{self.name} unequipped {item_name}.]")
            return True
        conn.close()
        print(f"[{self.name} does not have {item_name} to unequip.]")
        return False

    def cast_spell(self, spell_level: int, spell_name: str):
        if self.is_concentrating:
            self.break_concentration()

        # Check if the spell requires concentration
        spell_data = next((s for s in self.spells if s['name'] == spell_name), None)
        if spell_data and "Concentration" in spell_data['duration']:
            conn = get_db_connection()
            conn.execute("UPDATE characters SET is_concentrating = 1 WHERE id = ?", (self._id,))
            conn.commit()
            conn.close()
            self.refresh_cache()
            print(f"[{self.name} is now concentrating on {spell_name}.]")

        if spell_level == 0: return True
        slot_key_current = f"spell_slots_l{spell_level}_current"
        conn = get_db_connection()
        row = conn.execute(f"SELECT {slot_key_current} FROM characters WHERE id = ?", (self._id,)).fetchone()
        current_slots = row[slot_key_current] if row else 0
        if current_slots > 0:
            conn.execute(f"UPDATE characters SET {slot_key_current} = ? WHERE id = ?", (current_slots - 1, self._id))
            conn.commit()
            conn.close()
            self.refresh_cache()
            return True
        conn.close()
        return False
    
    def use_item(self, item_name: str) -> bool:
        from .data import STORE_INVENTORY # Import here to avoid circular dependency
        conn = get_db_connection()
        
        # Check if item is in inventory
        item_in_inventory = next((item for item, _ in self.inventory_items if item == item_name), None)
        if not item_in_inventory:
            print(f"[{self.name} does not have {item_name} in inventory.]")
            conn.close()
            return False

        # Check if item is a consumable
        item_data = STORE_INVENTORY.get(item_name)
        if not item_data or "consumable_effect" not in item_data:
            print(f"[{item_name} is not a consumable item.]")
            conn.close()
            return False
        
        effect = item_data["consumable_effect"]
        if effect["type"] == "heal":
            healing_roll_notation = effect["amount"]
            total_healing, _ = roll_dice(healing_roll_notation)
            self.update_hp(total_healing)
            print(f"[{self.name} used {item_name} and healed {total_healing} HP!]")

            # Decrement/remove from inventory
            cursor = conn.cursor()
            cursor.execute("SELECT id, quantity FROM inventory WHERE character_id = ? AND item_name = ?", (self._id, item_name))
            item_row = cursor.fetchone()
            if item_row and item_row['quantity'] > 1:
                cursor.execute("UPDATE inventory SET quantity = ? WHERE id = ?", (item_row['quantity'] - 1, item_row['id']))
            elif item_row and item_row['quantity'] == 1:
                cursor.execute("DELETE FROM inventory WHERE id = ?", (item_row['id'],))
            conn.commit()
            conn.close()
            self.refresh_cache()
            return True
        
        conn.close()
        return False

    def __str__(self):
        mods = self.ability_modifiers
        text = f"--- Character Sheet: {self.name} ({self.class_name} {self.level}) ---\n"
        text += f"AC: {self.armor_class} | HP: {self.current_hp}/{self.max_hp} | Initiative: {self.initiative:+} | Prof Bonus: +{self.proficiency_bonus}\n"
        text += f"Hit Dice: {self.hit_dice_current}/{self.hit_dice_max} ({self.hit_die_type}) | Gold: {self.gold} gp\n\n"
        if self.conditions:
            text += "--- Conditions ---\n"
            text += ", ".join(c['condition_name'] for c in self.conditions) + "\n\n"
        text += "--- Abilities ---\n"
        text += f"STR {self.stats['STR']}({mods['STR']:+}) | DEX {self.stats['DEX']}({mods['DEX']:+}) | CON {self.stats['CON']}({mods['CON']:+}) | INT {self.stats['INT']}({mods['INT']:+}) | WIS {self.stats['WIS']}({mods['WIS']:+}) | CHA {self.stats['CHA']}({mods['CHA']:+})\n\n"
        text += "--- Saving Throws ---\n"
        for stat in self.stats.keys(): text += f"  {stat}: {self.get_saving_throw_modifier(stat):+} {'(P)' if f'{stat.title()} Saving Throw' in self.proficiencies else ''}\n"
        text += "\n--- Skills ---\n"
        for skill, ability in sorted(SKILL_TO_ABILITY_MAP.items()): text += f"  {skill} ({ability}): {self.get_skill_modifier(skill):+} {'(P)' if skill in self.proficiencies else ''}\n"
        text += f"\nPassive Perception: {self.passive_perception}\n\n"
        text += "--- Attacks ---\n"
        for item_name, _ in self.inventory_items: # Iterate through all items
            if item_name in WEAPON_DATA: text += f"  {item_name}: +{self.get_attack_bonus(item_name)} to hit, {self.get_damage_roll(item_name)}\n"
        
        if self.spellcasting_ability:
            text += "\n--- Spellcasting ---\n"
            text += f"Ability: {self.spellcasting_ability} | Save DC: {self.spell_save_dc} | Attack Bonus: +{self.spell_attack_bonus}\n"
            slots = self.spell_slots
            slot_display = " | ".join([f"L{i}: {s['current']}/{s['max']}" for i, s in slots.items() if s['max'] > 0])
            if slot_display: text += "Slots: " + slot_display + "\n"
            cantrips = sorted([s['name'] for s in self.spells if s['level'] == 0])
            spells = sorted([s['name'] for s in self.spells if s['level'] > 0])
            if cantrips: text += f"Cantrips: {', '.join(cantrips)}\n"
            if spells: text += f"Spells: {', '.join(spells)}\n"
        text += "\n--- Inventory ---\n"
        if self.inventory_items:
            for item_name, equipped_status in self.inventory_items:
                status = "(Equipped)" if equipped_status else ""
                text += f"- {item_name} {status}\n"
        else:
            text += "  (Empty)\n"

        return text

    def get_prompt_summary(self) -> str:
        mods = self.ability_modifiers
        summary = f"--- Character: {self.name} ({self.class_name} {self.level}) ---\n"
        if self.sex:
            summary += f"Sex: {self.sex}\n"
        if self.pronouns:
            summary += f"Pronouns: {self.pronouns}\n"
        summary += f"AC: {self.armor_class} | HP: {self.current_hp}/{self.max_hp} | Initiative: {self.initiative:+} | Proficiency Bonus: +{self.proficiency_bonus}\n"
        summary += f"Gold: {self.gold} gp\n"
        summary += f"Stats: STR {self.stats['STR']}({mods['STR']:+}), DEX {self.stats['DEX']}({mods['DEX']:+}), CON {self.stats['CON']}({mods['CON']:+}), INT {self.stats['INT']}({mods['INT']:+}), WIS {self.stats['WIS']}({mods['WIS']:+}), CHA {self.stats['CHA']}({mods['CHA']:+})\n"
        summary += f"Proficiencies: {', '.join(self.proficiencies)}\n"
        summary += f"Passive Perception: {self.passive_perception}\n"
        if self.conditions:
            summary += f"Conditions: {', '.join(c['condition_name'] for c in self.conditions)}\n"
        if self.spellcasting_ability:
            summary += f"Spellcasting Ability: {self.spellcasting_ability}, Spell Save DC: {self.spell_save_dc}, Spell Attack: +{self.spell_attack_bonus}\n"
            summary += "Known Spells: " + ", ".join([s['name'] for s in self.spells]) + "\n"
        summary += f"Equipped Items: {', '.join(self.equipped_items)}\n"
        summary += f"Unequipped Items: {', '.join(self.unequipped_items)}\n"
        summary += "--- End Summary ---\n"
        return summary
