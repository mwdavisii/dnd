# dnd/data.py
import json
import os
import math
from .database import get_db_connection
from .data import WEAPON_DATA, SKILL_TO_ABILITY_MAP, ARMOR_DATA, CLASS_DATA

class CharacterSheet:
    def __init__(self, name: str):
        self._name = name
        self._id = self._get_id()
        self.refresh_cache()

    def refresh_cache(self):
        self._proficiencies_cache = self._fetch_proficiencies()
        self._inventory_cache = self._fetch_inventory()
        self._spells_cache = self._fetch_spells()

    def _fetch_proficiencies(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT p.name FROM proficiencies p JOIN character_proficiencies cp ON p.id = cp.proficiency_id WHERE cp.character_id = ?", (self._id,)).fetchall()
        conn.close()
        return [row['name'] for row in rows]

    def _fetch_inventory(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT item_name FROM inventory WHERE character_id = ?", (self._id,)).fetchall()
        conn.close()
        return [row['item_name'] for row in rows]

    def _fetch_spells(self):
        conn = get_db_connection()
        rows = conn.execute("SELECT s.* FROM spells s JOIN character_spells cs ON s.id = cs.spell_id WHERE cs.character_id = ?", (self._id,)).fetchall()
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
    def inventory(self): return self._inventory_cache
    @property
    def proficiencies(self): return self._proficiencies_cache
    @property
    def spells(self): return self._spells_cache
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
        for item_name in self.inventory:
            if item_name in ARMOR_DATA and ARMOR_DATA[item_name]['type'] != 'shield':
                armor = ARMOR_DATA[item_name]
                if armor['type'] == 'light': ac = armor['ac'] + dex_mod
                elif armor['type'] == 'medium': ac = armor['ac'] + min(dex_mod, armor.get('dex_cap', 2))
                elif armor['type'] == 'heavy': ac = armor['ac']
                break
        if "Shield" in self.inventory: ac += ARMOR_DATA["Shield"]["ac"]
        return ac
    @property
    def passive_perception(self): return 10 + self.get_skill_modifier("Perception")

    def get_saving_throw_modifier(self, ability_name: str):
        mod = self.ability_modifiers.get(ability_name.upper(), 0)
        if f"{ability_name.title()} Saving Throw" in self.proficiencies: mod += self.proficiency_bonus
        return mod

    def get_skill_modifier(self, skill_name: str):
        ability = SKILL_TO_ABILITY_MAP.get(skill_name.title())
        if not ability: return 0
        mod = self.ability_modifiers.get(ability, 0)
        if skill_name.title() in self.proficiencies: mod += self.proficiency_bonus
        return mod

    def get_attack_bonus(self, weapon_name: str):
        weapon_info = WEAPON_DATA.get(weapon_name)
        if not weapon_info: return 0
        mods = self.ability_modifiers
        ability_mod = mods.get("DEX", 0) if any(p in weapon_info.get("properties", []) for p in ["Ranged", "Thrown"]) else mods.get("STR", 0)
        if "Finesse" in weapon_info["properties"]: ability_mod = max(mods.get("STR", 0), mods.get("DEX", 0))
        is_proficient = any(p in self.proficiencies for p in [weapon_name, "Simple Weapons", "Martial Weapons"])
        return ability_mod + self.proficiency_bonus if is_proficient else ability_mod

    def get_damage_roll(self, weapon_name: str):
        weapon_info = WEAPON_DATA.get(weapon_name)
        if not weapon_info: return "N/A"
        mods = self.ability_modifiers
        ability_mod = mods.get("DEX", 0) if any(p in weapon_info.get("properties", []) for p in ["Ranged", "Thrown"]) else mods.get("STR", 0)
        if "Finesse" in weapon_info["properties"]: ability_mod = max(mods.get("STR", 0), mods.get("DEX", 0))
        damage_die, damage_type = weapon_info['damage'], weapon_info['type']
        return f"{damage_die} {ability_mod:+} {damage_type}" if ability_mod != 0 else f"{damage_die} {damage_type}"

    def update_hp(self, amount: int):
        new_hp = min(self.current_hp + amount, self.max_hp)
        new_hp = max(0, new_hp)
        conn = get_db_connection()
        conn.execute("UPDATE characters SET hp_current = ? WHERE id = ?", (new_hp, self._id))
        conn.commit()
        conn.close()

    def level_up(self):
        new_level = self.level + 1
        new_max_hp = self.max_hp + 5 # Simplified
        new_prof_bonus = self.proficiency_bonus
        if new_level in [5, 9, 13, 17]: new_prof_bonus += 1
        conn = get_db_connection()
        conn.execute("UPDATE characters SET level = ?, hp_max = ?, hp_current = ?, proficiency_bonus = ? WHERE id = ?", (new_level, new_max_hp, new_max_hp, new_prof_bonus, self._id))
        conn.commit()
        conn.close()
        self.refresh_cache()

    def cast_spell(self, spell_level: int):
        if spell_level == 0: return True
        slot_key = f"spell_slots_l{spell_level}_current"
        conn = get_db_connection()
        row = conn.execute(f"SELECT {slot_key} FROM characters WHERE id = ?", (self._id,)).fetchone()
        current_slots = row[slot_key] if row else 0
        if current_slots > 0:
            conn.execute(f"UPDATE characters SET {slot_key} = ? WHERE id = ?", (current_slots - 1, self._id))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False

    def __str__(self):
        mods = self.ability_modifiers
        text = f"--- Character Sheet: {self.name} ({self.class_name} {self.level}) ---\n"
        text += f"AC: {self.armor_class} | HP: {self.current_hp}/{self.max_hp} | Initiative: {self.initiative:+} | Prof Bonus: +{self.proficiency_bonus}\n"
        text += f"Hit Dice: {self.hit_dice_current}/{self.level} ({self.hit_die_type})\n\n"
        text += "--- Abilities ---\n"
        text += f"STR {self.stats['STR']}({mods['STR']:+}) | DEX {self.stats['DEX']}({mods['DEX']:+}) | CON {self.stats['CON']}({mods['CON']:+}) | INT {self.stats['INT']}({mods['INT']:+}) | WIS {self.stats['WIS']}({mods['WIS']:+}) | CHA {self.stats['CHA']}({mods['CHA']:+})\n\n"
        text += "--- Saving Throws ---\n"
        for stat in self.stats.keys(): text += f"  {stat}: {self.get_saving_throw_modifier(stat):+} {'(P)' if f'{stat.title()} Saving Throw' in self.proficiencies else ''}\n"
        text += "\n--- Skills ---\n"
        for skill, ability in sorted(SKILL_TO_ABILITY_MAP.items()): text += f"  {skill} ({ability}): {self.get_skill_modifier(skill):+} {'(P)' if skill in self.proficiencies else ''}\n"
        text += f"\nPassive Perception: {self.passive_perception}\n\n"
        text += "--- Attacks ---\n"
        for item in self.inventory:
            if item in WEAPON_DATA: text += f"  {item}: +{self.get_attack_bonus(item)} to hit, {self.get_damage_roll(item)}\n"
        
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
        return text

    def get_prompt_summary(self) -> str:
        mods = self.ability_modifiers
        summary = f"--- Character: {self.name} ({self.class_name} {self.level}) ---\n"
        summary += f"AC: {self.armor_class} | HP: {self.current_hp}/{self.max_hp} | Initiative: {self.initiative:+} | Proficiency Bonus: +{self.proficiency_bonus}\n"
        summary += f"Stats: STR {self.stats['STR']}({mods['STR']:+}), DEX {self.stats['DEX']}({mods['DEX']:+}), CON {self.stats['CON']}({mods['CON']:+}), INT {self.stats['INT']}({mods['INT']:+}), WIS {self.stats['WIS']}({mods['WIS']:+}), CHA {self.stats['CHA']}({mods['CHA']:+})\n"
        summary += f"Proficiencies: {', '.join(self.proficiencies)}\n"
        summary += f"Passive Perception: {self.passive_perception}\n"
        if self.spellcasting_ability:
            summary += f"Spellcasting Ability: {self.spellcasting_ability}, Spell Save DC: {self.spell_save_dc}, Spell Attack: +{self.spell_attack_bonus}\n"
            summary += "Known Spells: " + ", ".join([s['name'] for s in self.spells]) + "\n"
        summary += f"Inventory: {', '.join(self.inventory)}\n"
        summary += "--- End Summary ---\n"
        return summary