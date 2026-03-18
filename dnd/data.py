# dnd/data.py

SKILL_TO_ABILITY_MAP = { "Acrobatics": "DEX", "Animal Handling": "WIS", "Arcana": "INT", "Athletics": "STR", "Deception": "CHA", "History": "INT", "Insight": "WIS", "Intimidation": "CHA", "Investigation": "INT", "Medicine": "WIS", "Nature": "INT", "Perception": "WIS", "Performance": "CHA", "Persuasion": "CHA", "Religion": "INT", "Sleight of Hand": "DEX", "Stealth": "DEX", "Survival": "WIS" }
WEAPON_DATA = { "Dagger": {"damage": "1d4", "type": "Piercing", "properties": ["Finesse", "Light", "Thrown"]}, "Handaxe": {"damage": "1d6", "type": "Slashing", "properties": ["Light", "Thrown"]}, "Mace": {"damage": "1d6", "type": "Bludgeoning", "properties": []}, "Quarterstaff": {"damage": "1d6", "type": "Bludgeoning", "properties": ["Versatile (1d8)"]}, "Scimitar": {"damage": "1d6", "type": "Slashing", "properties": ["Finesse", "Light"]}, "Greataxe": {"damage": "1d12", "type": "Slashing", "properties": ["Heavy", "Two-Handed"]}, "Longsword": {"damage": "1d8", "type": "Slashing", "properties": ["Versatile (1d10)"]}, "Rapier": {"damage": "1d8", "type": "Piercing", "properties": ["Finesse"]}, "Shortsword": {"damage": "1d6", "type": "Piercing", "properties": ["Finesse", "Light"]}, "Light Crossbow": {"damage": "1d8", "type": "Piercing", "properties": ["Ammunition", "Loading", "Two-Handed"]}, "Dart": {"damage": "1d4", "type": "Piercing", "properties": ["Finesse", "Thrown"]}, "Longbow": {"damage": "1d8", "type": "Piercing", "properties": ["Ammunition", "Heavy", "Two-Handed"]}, }
ARMOR_DATA = { "Padded Armor": {"ac": 11, "type": "light"}, "Leather Armor": {"ac": 11, "type": "light"}, "Hide Armor": {"ac": 12, "type": "medium", "dex_cap": 2}, "Chain Shirt": {"ac": 13, "type": "medium", "dex_cap": 2}, "Chain Mail": {"ac": 16, "type": "heavy"}, "Plate Armor": {"ac": 18, "type": "heavy"}, "Shield": {"ac": 2, "type": "shield"} }
SPELL_DATA = { "Fire Bolt": { "level": 0, "school": "Evocation", "casting_time": "1 action", "range": "120 feet", "components": "V, S", "duration": "Instantaneous", "description": "You hurl a mote of fire..."}, "Mage Hand": { "level": 0, "school": "Conjuration", "casting_time": "1 action", "range": "30 feet", "components": "V, S", "duration": "1 minute", "description": "A spectral, floating hand appears..."}, "Light": { "level": 0, "school": "Evocation", "casting_time": "1 action", "range": "Touch", "components": "V, M (a firefly...)", "duration": "1 hour", "description": "You touch one object..."}, "Magic Missile": { "level": 1, "school": "Evocation", "casting_time": "1 action", "range": "120 feet", "components": "V, S", "duration": "Instantaneous", "description": "You create three glowing darts..."}, "Cure Wounds": { "level": 1, "school": "Evocation", "casting_time": "1 action", "range": "Touch", "components": "V, S", "duration": "Instantaneous", "description": "A creature you touch regains..."}, "Bless": { "level": 1, "school": "Enchantment", "casting_time": "1 action", "range": "30 feet", "components": "V, S, M (a sprinkle...)", "duration": "Concentration, up to 1 minute", "description": "You bless up to three creatures..."}, "Shield": { "level": 1, "school": "Abjuration", "casting_time": "1 reaction", "range": "Self", "components": "V, S", "duration": "1 round", "description": "An invisible barrier of magical force appears and protects you. Until the start of your next turn, you have a +5 bonus to AC, including against the triggering attack, and you take no damage from magic missile."}, "Thunderwave": { "level": 1, "school": "Evocation", "casting_time": "1 action", "range": "Self (15-foot cube)", "components": "V, S", "duration": "Instantaneous", "description": "A wave of thunderous force sweeps out from you. Each creature in a 15-foot cube originating from you must make a Constitution saving throw. On a failed save, a creature takes 2d8 thunder damage and is pushed 10 feet away from you. On a successful save, the creature takes half as much damage and is not pushed. In addition, unsecured objects that are completely within the area of effect are automatically pushed 10 feet away from you by the spell's effect, and the spell emits a thunderous boom audible out to 300 feet."} }
MONSTER_DATA = {
    "Bandit": {"initiative": 1},
    "Cultist": {"initiative": 1},
    "Goblin": {"initiative": 2},
    "Guard": {"initiative": 1},
    "Kobold": {"initiative": 2},
    "Orc": {"initiative": 1},
    "Skeleton": {"initiative": 2},
    "Wolf": {"initiative": 2},
}

CLASS_PROFICIENCIES = { "Barbarian": ["Strength Saving Throw", "Constitution Saving Throw", "Athletics", "Survival"], "Bard": ["Dexterity Saving Throw", "Charisma Saving Throw", "Acrobatics", "Performance", "Persuasion"], "Cleric": ["Wisdom Saving Throw", "Charisma Saving Throw", "Insight", "Religion"], "Druid": ["Intelligence Saving Throw", "Wisdom Saving Throw", "Nature", "Animal Handling"], "Fighter": ["Strength Saving Throw", "Constitution Saving Throw", "Athletics", "Intimidation"], "Monk": ["Strength Saving Throw", "Dexterity Saving Throw", "Acrobatics", "Stealth"], "Paladin": ["Wisdom Saving Throw", "Charisma Saving Throw", "Athletics", "Persuasion"], "Ranger": ["Strength Saving Throw", "Dexterity Saving Throw", "Stealth", "Survival"], "Rogue": ["Dexterity Saving Throw", "Intelligence Saving Throw", "Acrobatics", "Stealth", "Sleight of Hand"], "Sorcerer": ["Constitution Saving Throw", "Charisma Saving Throw", "Arcana", "Deception"], "Warlock": ["Wisdom Saving Throw", "Charisma Saving Throw", "Arcana", "Deception"], "Wizard": ["Intelligence Saving Throw", "Wisdom Saving Throw", "Arcana", "History"], }
BACKGROUND_DATA = { "Acolyte": {"proficiencies": ["Insight", "Religion"], "tools": ["Cartographer's Tools"], "abilities": ["INT", "WIS", "CHA"], "description": "You have spent your life in service to a temple."}, "Criminal": {"proficiencies": ["Deception", "Stealth"], "tools": ["Thieves' Tools"], "abilities": ["DEX", "CON", "INT"], "description": "You have a history of breaking the law."}, "Sage": {"proficiencies": ["Arcana", "History"], "tools": ["Calligrapher's Supplies"], "abilities": ["CON", "INT", "WIS"], "description": "You spent years learning the lore of the multiverse."}, "Soldier": {"proficiencies": ["Athletics", "Intimidation"], "tools": ["Playing Card Set"], "abilities": ["STR", "DEX", "CON"], "description": "You served in an army and know military discipline."}, }
STANDARD_ARRAY_BY_CLASS = { "Barbarian": {"STR": 15, "DEX": 13, "CON": 14, "INT": 10, "WIS": 12, "CHA": 8}, "Bard": {"STR": 8, "DEX": 14, "CON": 12, "INT": 13, "WIS": 10, "CHA": 15}, "Cleric": {"STR": 14, "DEX": 8, "CON": 13, "INT": 10, "WIS": 15, "CHA": 12}, "Druid": {"STR": 8, "DEX": 12, "CON": 14, "INT": 13, "WIS": 15, "CHA": 10}, "Fighter": {"STR": 15, "DEX": 14, "CON": 13, "INT": 8, "WIS": 10, "CHA": 12}, "Monk": {"STR": 12, "DEX": 15, "CON": 13, "INT": 10, "WIS": 14, "CHA": 8}, "Paladin": {"STR": 15, "DEX": 10, "CON": 13, "INT": 8, "WIS": 12, "CHA": 14}, "Ranger": {"STR": 12, "DEX": 15, "CON": 13, "INT": 8, "WIS": 14, "CHA": 10}, "Rogue": {"STR": 12, "DEX": 15, "CON": 13, "INT": 14, "WIS": 10, "CHA": 8}, "Sorcerer": {"STR": 10, "DEX": 13, "CON": 14, "INT": 8, "WIS": 12, "CHA": 15}, "Warlock": {"STR": 8, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 15}, "Wizard": {"STR": 8, "DEX": 12, "CON": 13, "INT": 15, "WIS": 14, "CHA": 10}, }
CLASS_DATA = { "Barbarian": {"hp_base": 12, "hit_die": "d12", "inventory": ["Greataxe", "Handaxe"], "proficiencies": CLASS_PROFICIENCIES["Barbarian"], "spellcasting_ability": None, "starting_gold": 100}, "Fighter": {"hp_base": 10, "hit_die": "d10", "inventory": ["Longsword", "Shield", "Chain Mail"], "proficiencies": CLASS_PROFICIENCIES["Fighter"], "spellcasting_ability": None, "starting_gold": 100}, "Monk": {"hp_base": 8, "hit_die": "d8", "inventory": ["Shortsword", "Dart"], "proficiencies": CLASS_PROFICIENCIES["Monk"], "spellcasting_ability": None, "starting_gold": 100}, "Rogue": {"hp_base": 8, "hit_die": "d8", "inventory": ["Shortsword", "Dagger", "Leather Armor", "Thieves' Tools"], "proficiencies": CLASS_PROFICIENCIES["Rogue"], "spellcasting_ability": None, "starting_gold": 100}, "Bard": {"hp_base": 8, "hit_die": "d8", "inventory": ["Rapier", "Lute", "Leather Armor"], "proficiencies": CLASS_PROFICIENCIES["Bard"], "spellcasting_ability": "CHA", "cantrips": ["Mage Hand"], "spells": ["Cure Wounds"], "spell_slots_l1": 2, "starting_gold": 100}, "Cleric": {"hp_base": 8, "hit_die": "d8", "inventory": ["Mace", "Shield", "Holy Symbol"], "proficiencies": CLASS_PROFICIENCIES["Cleric"], "spellcasting_ability": "WIS", "cantrips": ["Light"], "spells": ["Bless", "Cure Wounds"], "spell_slots_l1": 2, "starting_gold": 100}, "Druid": {"hp_base": 8, "hit_die": "d8", "inventory": ["Scimitar", "Wooden Shield"], "proficiencies": CLASS_PROFICIENCIES["Druid"], "spellcasting_ability": "WIS", "cantrips": [], "spells": ["Cure Wounds"], "spell_slots_l1": 2, "starting_gold": 100}, "Paladin": {"hp_base": 10, "hit_die": "d10", "inventory": ["Longsword", "Shield", "Chain Mail"], "proficiencies": CLASS_PROFICIENCIES["Paladin"], "spellcasting_ability": "CHA", "cantrips": [], "spells": [], "spell_slots_l1": 0, "starting_gold": 100}, "Ranger": {"hp_base": 10, "hit_die": "d10", "inventory": ["Longbow", "Shortsword", "Leather Armor"], "proficiencies": CLASS_PROFICIENCIES["Ranger"], "spellcasting_ability": "WIS", "cantrips": [], "spells": [], "spell_slots_l1": 0, "starting_gold": 100}, "Sorcerer": {"hp_base": 6, "hit_die": "d6", "inventory": ["Light Crossbow", "Dagger"], "proficiencies": CLASS_PROFICIENCIES["Sorcerer"], "spellcasting_ability": "CHA", "cantrips": ["Fire Bolt"], "spells": ["Magic Missile"], "spell_slots_l1": 2, "starting_gold": 100}, "Warlock": {"hp_base": 8, "hit_die": "d8", "inventory": ["Light Crossbow", "Dagger", "Leather Armor"], "proficiencies": CLASS_PROFICIENCIES["Warlock"], "spellcasting_ability": "CHA", "cantrips": ["Fire Bolt"], "spells": ["Magic Missile"], "spell_slots_l1": 1, "starting_gold": 100}, "Wizard": {"hp_base": 6, "hit_die": "d6", "inventory": ["Quarterstaff", "Spellbook"], "proficiencies": CLASS_PROFICIENCIES["Wizard"], "spellcasting_ability": "INT", "cantrips": ["Fire Bolt", "Mage Hand"], "spells": ["Magic Missile"], "spell_slots_l1": 2, "starting_gold": 100}, }
DESCRIPTIVE_WORDS = { "STR": {"high": "Muscular, Sinewy, Protective, Direct", "low": "Weak, Slight, Self-conscious, Indirect"}, "DEX": {"high": "Lithe, Dynamic, Fidgety, Poised", "low": "Jittery, Clumsy, Hesitant, Unsteady"}, "CON": {"high": "Energetic, Hale, Hearty, Stable", "low": "Frail, Squeamish, Lethargic, Fragile"}, "INT": {"high": "Decisive, Logical, Informative, Curious", "low": "Artless, Illogical, Uninformed, Frivolous"}, "WIS": {"high": "Serene, Considerate, Attentive, Wary", "low": "Rash, Distracted, Oblivious, Naive"}, "CHA": {"high": "Charming, Commanding, Hilarious, Inspiring", "low": "Pedantic, Humorless, Reserved, Tactless"}, }

STORE_INVENTORY = {
    "Healing Potion": {"cost": 50, "description": "Restores 2d4+2 Hit Points", "consumable_effect": {"type": "heal", "amount": "2d4+2"}},
    "Torch": {"cost": 1, "description": "Provides light for 1 hour"},
    "Rope (50ft)": {"cost": 1, "description": "Standard adventuring rope"},
    "Rations (1 day)": {"cost": 0.5, "description": "Food for one day"},
    "Leather Armor": {"cost": 10, "description": "Light armor, AC 11 + Dex mod"},
    "Shield": {"cost": 10, "description": "Adds +2 to AC"},
    "Longsword": {"cost": 15, "description": "Versatile martial weapon"},
}

HELP_TOPICS = {
    "commands": [
        "/sheet: show your current stats, AC, HP, spells, and inventory",
        "/attack <weapon>: show the to-hit and damage math for one weapon attack",
        "/cast <spell>: show spellcasting math, then cast a known spell",
        "/inventory: list equipped gear, pack items, and current gold",
        "/journal: show your current location, objective, and active quests",
        "/map: show where you are and known nearby locations",
        "/teach [on|off]: toggle teaching mode explanations",
        "/rules <topic>: show a quick rules reference",
    ],
    "combat": [
        "Use /attack <weapon> to see the full attack formula before narrating your action.",
        "Your Armor Class (AC) is the number enemies must meet or beat to hit you.",
        "Damage is rolled only after an attack hits.",
        "Use /rules attacks or /rules spellcasting for the underlying math.",
    ],
    "spells": [
        "Use /cast <spell> for spells you know.",
        "Cantrips do not spend spell slots.",
        "Leveled spells spend one slot of the spell's level.",
        "Some spells use a spell attack roll; others force a saving throw against your save DC.",
    ],
    "exploration": [
        "Type free-form actions such as 'inspect the altar' or 'search the room'.",
        "Use /journal to review goals and /map to review known locations.",
        "Suggested actions appear after scenes to help if you are unsure what to do next.",
    ],
}

_BEAT_PHASE = {
    "hook": "opening",
    "complication": "midgame",
    "climax": "climax",
    "resolution": "resolution",
}

MAX_LEVEL = 20  # D&D 5e level cap

RULES_REFERENCE = {
    "advantage": "Advantage means rolling two d20s and using the higher result. Disadvantage uses the lower result.",
    "saving-throws": "A saving throw is a defensive d20 roll. Roll 1d20, add the listed save modifier, and try to meet or beat the DC.",
    "attacks": "Weapon attacks usually use 1d20 + ability modifier + proficiency if you are proficient. Meet or beat the target's AC to hit.",
    "spellcasting": "Spell attack rolls use 1d20 + spellcasting ability modifier + proficiency. Spell save DC is 8 + proficiency + spellcasting ability modifier.",
    "skill-checks": "Skill checks use 1d20 + the linked ability modifier, plus proficiency if you are trained in that skill.",
    "resting": "A short rest can spend Hit Dice to recover HP. A long rest restores HP, refreshes spell slots, and recovers Hit Dice.",
    "sneak-attack": "Sneak Attack adds extra damage to a rogue weapon hit when the normal rogue trigger conditions are met. It does not change the attack roll formula.",
}
