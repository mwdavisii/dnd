# dnd/character_creator.py
import json
import os
import math
from .database import get_db_connection
from .data import (
    CLASS_DATA, BACKGROUND_DATA, STANDARD_ARRAY_BY_CLASS, DESCRIPTIVE_WORDS
)
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def _get_modifier_from_score(score):
    return math.floor((score - 10) / 2)

def _handle_proficiencies(conn, char_id, class_profs, bg_profs):
    cursor = conn.cursor()
    all_prof_names = set(class_profs + bg_profs)
    for prof_name in all_prof_names:
        prof_type = 'saving_throw' if 'Saving Throw' in prof_name else 'tool' if 'Tools' in prof_name or 'Supplies' in prof_name or 'Set' in prof_name else 'skill'
        cursor.execute("SELECT id FROM proficiencies WHERE name = ?", (prof_name,))
        row = cursor.fetchone()
        if row: prof_id = row['id']
        else:
            cursor.execute("INSERT INTO proficiencies (name, type) VALUES (?, ?)", (prof_name, prof_type))
            prof_id = cursor.lastrowid
        cursor.execute("INSERT INTO character_proficiencies (character_id, proficiency_id) VALUES (?, ?)", (char_id, prof_id))

def _handle_spells(conn, char_id, class_info):
    cursor = conn.cursor()
    starting_spells = class_info.get("cantrips", []) + class_info.get("spells", [])
    if not starting_spells: return
    for spell_name in starting_spells:
        cursor.execute("SELECT id FROM spells WHERE name = ?", (spell_name,))
        row = cursor.fetchone()
        if row:
            spell_id = row['id']
            cursor.execute("INSERT INTO character_spells (character_id, spell_id) VALUES (?, ?)", (char_id, spell_id))
        else: print(f"Warning: Spell '{spell_name}' not found in master spell list.")

def choose_companion_count(max_companions: int) -> int:
    clear_screen()
    print("--- Choose your party size ---")
    print("0 companions: explore alone and watch the DM carry the full scene.")
    print(f"1-{max_companions} companions: add AI party members you can talk to with 'ask <npc> ...'.")
    choice = None
    while choice is None:
        raw = input(f"How many companions do you want? (0-{max_companions})\n> ").strip()
        try:
            parsed = int(raw)
            if 0 <= parsed <= max_companions:
                choice = parsed
        except ValueError:
            continue
    return choice

def run_character_creation():
    conn = get_db_connection()
    cursor = conn.cursor()
    clear_screen()
    char_name = ""
    while not char_name: char_name = input("--- What is your character's name? ---\n> ").strip()
    clear_screen()
    print(f"--- {char_name}, choose your class ---")
    class_list = list(CLASS_DATA.keys())
    for i, name in enumerate(class_list): print(f"{i+1}. {name}")
    class_choice_idx = -1
    while not (0 <= class_choice_idx < len(class_list)):
        try:
            choice = int(input(f"> "))
            if 1 <= choice <= len(class_list): class_choice_idx = choice - 1
        except ValueError: continue
    chosen_class_name = class_list[class_choice_idx]
    class_info = CLASS_DATA[chosen_class_name]
    stats = STANDARD_ARRAY_BY_CLASS[chosen_class_name].copy()
    clear_screen()
    print("--- Choose your background ---")
    bg_list = list(BACKGROUND_DATA.keys())
    for i, name in enumerate(bg_list): print(f"{i+1}. {name} - {BACKGROUND_DATA[name]['description']}")
    bg_choice_idx = -1
    while not (0 <= bg_choice_idx < len(bg_list)):
        try:
            choice = int(input(f"> "))
            if 1 <= choice <= len(bg_list): bg_choice_idx = choice - 1
        except ValueError: continue
    chosen_bg_name = bg_list[bg_choice_idx]
    bg_info = BACKGROUND_DATA[chosen_bg_name]
    clear_screen()
    print("--- Adjust your Ability Scores ---")
    eligible_abilities = bg_info['abilities']
    while True:
        print("\nYour current stats:", stats)
        print(f"Your background suggests adjusting: {', '.join(eligible_abilities)}")
        choice = input("Choose an option: [1] +2/+1  [2] +1/+1/+1\n> ").strip()
        if choice == '1':
            while True:
                plus_2 = input(f"Which ability gets +2? ({', '.join(eligible_abilities)}) > ").upper()
                if plus_2 in eligible_abilities:
                    stats[plus_2] += 2
                    break
            while True:
                plus_1 = input(f"Which different ability gets +1? ({', '.join(eligible_abilities)}) > ").upper()
                if plus_1 in eligible_abilities and plus_1 != plus_2:
                    stats[plus_1] += 1
                    break
            break
        elif choice == '2':
            choices = []
            for i in range(3):
                while True:
                    prompt = f"Choose your {'first' if i==0 else 'next'} +1 ability ({', '.join(eligible_abilities)}) > "
                    c = input(prompt).upper()
                    if c in eligible_abilities and c not in choices:
                        stats[c] += 1
                        choices.append(c)
                        break
            break
    con_modifier = _get_modifier_from_score(stats["CON"])
    max_hp = class_info['hp_base'] + con_modifier
    l1_slots = class_info.get('spell_slots_l1', 0)
    starting_gold = class_info.get('starting_gold', 0)
    try:
        cursor.execute( "INSERT INTO characters (name, class_name, hp_current, hp_max, stats, level, proficiency_bonus, hit_die_type, hit_dice_max, hit_dice_current, spell_slots_l1_max, spell_slots_l1_current, gold, is_player) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (char_name, chosen_class_name, max_hp, max_hp, json.dumps(stats), 1, 2, class_info['hit_die'], 1, 1, l1_slots, l1_slots, starting_gold, 1) )
        char_id = cursor.lastrowid
        all_profs = class_info['proficiencies'] + bg_info['proficiencies'] + bg_info['tools']
        _handle_proficiencies(conn, char_id, all_profs, [])
        _handle_spells(conn, char_id, class_info)
        for item in class_info['inventory']:
            cursor.execute("INSERT INTO inventory (character_id, item_name, quantity) VALUES (?, ?, ?)", (char_id, item, 1))
        conn.commit()
        conn.close()
        clear_screen()
        print(f"--- Character '{char_name}' the {chosen_class_name} ({chosen_bg_name}) Created! ---")
        print("\nFinal Stats:", stats)
        highest_stat = max(stats, key=stats.get)
        lowest_stat = min(stats, key=stats.get)
        print("\nConsider what these scores mean for your character:")
        print(f"  With a high {highest_stat}, they might be: {DESCRIPTIVE_WORDS[highest_stat]['high']}")
        print(f"  With a low {lowest_stat}, they might be: {DESCRIPTIVE_WORDS[lowest_stat]['low']}")

        print("\n--- Final Details ---")
        print("Consider these final questions about your character. The answers are for you alone.")
        print("  - Who raised you? Who was your dearest childhood friend?")
        print("  - Have you fallen in love? Do you have a family?")
        print("  - What is your deepest fear?")
        print("  - What do you seek on your adventures? (Wealth, glory, justice, power, etc.)")

        input("\nPress Enter to begin your adventure...")
        return char_name
    except Exception as e:
        print(f"\nAn error occurred while saving your character: {e}")
        conn.close()
        return None
