# tests/test_game.py
import pytest
from dnd.game import roll_dice

def test_roll_dice_simple():
    """Tests a simple d6 roll is within bounds."""
    for _ in range(100): # Roll 100 times to be reasonably sure
        total, _ = roll_dice('1d6')
        assert 1 <= total <= 6

def test_roll_dice_with_modifier():
    """Tests that a modifier is correctly applied."""
    for _ in range(100):
        total, _ = roll_dice('2d8+5')
        # 2*1+5=7, 2*8+5=21
        assert 7 <= total <= 21

def test_roll_dice_output_format():
    """Tests the explanation string format."""
    # We can't test the exact roll, but we can test the structure
    _, explanation = roll_dice('1d20+3')
    assert explanation.startswith("Rolling 1d20+3: (")
    assert "+ 3 =" in explanation

def test_roll_dice_invalid_input():
    """Tests that invalid dice notation raises an error."""
    with pytest.raises(ValueError):
        roll_dice('d-1')
    with pytest.raises(ValueError):
        roll_dice('abc')
    with pytest.raises(ValueError):
        roll_dice('3d')
