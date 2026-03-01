# dnd/game.py
import random
import re

def roll_dice(dice_notation: str) -> (int, str):
    """
    Rolls dice based on standard D&D notation (e.g., 'd20', '2d6+3').
    Returns a tuple of the total result and a string explaining the rolls.
    """
    match = re.match(r"(\d*)d(\d+)([\+\-]\d+)?", dice_notation.lower())
    if not match:
        raise ValueError("Invalid dice notation. Use format like 'd20' or '2d6+3'")

    num_dice = int(match.group(1)) if match.group(1) else 1
    die_type = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    rolls = [random.randint(1, die_type) for _ in range(num_dice)]
    total = sum(rolls) + modifier

    explanation = f"Rolling {dice_notation}: ({' + '.join(map(str, rolls))})"
    if modifier > 0:
        explanation += f" + {modifier}"
    elif modifier < 0:
        explanation += f" - {abs(modifier)}"
    
    explanation += f" = {total}"

    return total, explanation

