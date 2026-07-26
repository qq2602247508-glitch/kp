import pytest
from pydantic import ValidationError

from coc_kp_assistant.domain import (
    PercentileDice,
    RollDifficulty,
    RollRequest,
    SuccessLevel,
    resolve_percentile_roll,
)


@pytest.mark.parametrize(
    ("roll", "expected"),
    [
        (1, SuccessLevel.CRITICAL),
        (10, SuccessLevel.EXTREME),
        (24, SuccessLevel.HARD),
        (50, SuccessLevel.REGULAR),
        (51, SuccessLevel.FAILURE),
        (100, SuccessLevel.FUMBLE),
    ],
)
def test_success_levels(roll: int, expected: SuccessLevel) -> None:
    tens, units = divmod(roll if roll < 100 else 0, 10)
    result = resolve_percentile_roll(
        RollRequest(
            target_value=50,
            dice=PercentileDice(units_digit=units, tens_digits=(tens,)),
        )
    )

    assert result.success_level is expected


def test_bonus_die_selects_lower_result() -> None:
    result = resolve_percentile_roll(
        RollRequest(
            target_value=45,
            modifier_dice=-1,
            difficulty=RollDifficulty.HARD,
            dice=PercentileDice(units_digit=7, tens_digits=(6, 1)),
        )
    )

    assert result.total == 17
    assert result.selected_tens_digit == 1
    assert result.passed is True


def test_penalty_die_selects_higher_result() -> None:
    result = resolve_percentile_roll(
        RollRequest(
            target_value=70,
            modifier_dice=1,
            dice=PercentileDice(units_digit=2, tens_digits=(3, 8)),
        )
    )

    assert result.total == 82
    assert result.success_level is SuccessLevel.FAILURE


def test_modifier_requires_visible_tens_dice() -> None:
    with pytest.raises(ValidationError, match="tens dice count"):
        RollRequest(
            target_value=50,
            modifier_dice=-1,
            dice=PercentileDice(units_digit=4, tens_digits=(2,)),
        )
