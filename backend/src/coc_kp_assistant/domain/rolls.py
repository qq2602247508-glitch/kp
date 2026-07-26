from enum import IntEnum, StrEnum

from pydantic import Field, model_validator

from .base import DomainModel


class RollDifficulty(IntEnum):
    REGULAR = 1
    HARD = 2
    EXTREME = 3


class SuccessLevel(IntEnum):
    FUMBLE = -1
    FAILURE = 0
    REGULAR = 1
    HARD = 2
    EXTREME = 3
    CRITICAL = 4


class RollContext(StrEnum):
    STANDARD = "standard"
    OPPOSED = "opposed"
    COMBAT = "combat"
    SANITY = "sanity"


class PercentileDice(DomainModel):
    units_digit: int = Field(ge=0, le=9)
    tens_digits: tuple[int, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_tens_digits(self) -> "PercentileDice":
        if any(digit < 0 or digit > 9 for digit in self.tens_digits):
            raise ValueError("tens dice must contain digits from 0 to 9")
        return self


class RollRequest(DomainModel):
    target_value: int = Field(ge=0, le=100)
    difficulty: RollDifficulty = RollDifficulty.REGULAR
    modifier_dice: int = Field(default=0, ge=-2, le=2)
    dice: PercentileDice
    context: RollContext = RollContext.STANDARD
    pushed: bool = False

    @model_validator(mode="after")
    def require_matching_dice_count(self) -> "RollRequest":
        if len(self.dice.tens_digits) != abs(self.modifier_dice) + 1:
            raise ValueError("tens dice count must be one plus the modifier magnitude")
        if self.pushed and self.context is not RollContext.STANDARD:
            raise ValueError("pushed rolls are only represented for standard checks")
        return self


class RollResolution(DomainModel):
    selected_tens_digit: int = Field(ge=0, le=9)
    total: int = Field(ge=1, le=100)
    target_value: int = Field(ge=0, le=100)
    regular_threshold: int = Field(ge=0, le=100)
    hard_threshold: int = Field(ge=0, le=100)
    extreme_threshold: int = Field(ge=0, le=100)
    success_level: SuccessLevel
    required_level: RollDifficulty
    passed: bool
    pushed: bool


def _percentile_total(tens_digit: int, units_digit: int) -> int:
    total = tens_digit * 10 + units_digit
    return 100 if total == 0 else total


def resolve_percentile_roll(request: RollRequest) -> RollResolution:
    totals = [
        (_percentile_total(tens, request.dice.units_digit), tens)
        for tens in request.dice.tens_digits
    ]
    if request.modifier_dice < 0:
        total, selected_tens = min(totals)
    elif request.modifier_dice > 0:
        total, selected_tens = max(totals)
    else:
        total, selected_tens = totals[0]

    hard = request.target_value // 2
    extreme = request.target_value // 5
    fumble_floor = 96 if request.target_value < 50 else 100

    if total == 1:
        level = SuccessLevel.CRITICAL
    elif total >= fumble_floor:
        level = SuccessLevel.FUMBLE
    elif total <= extreme:
        level = SuccessLevel.EXTREME
    elif total <= hard:
        level = SuccessLevel.HARD
    elif total <= request.target_value:
        level = SuccessLevel.REGULAR
    else:
        level = SuccessLevel.FAILURE

    return RollResolution(
        selected_tens_digit=selected_tens,
        total=total,
        target_value=request.target_value,
        regular_threshold=request.target_value,
        hard_threshold=hard,
        extreme_threshold=extreme,
        success_level=level,
        required_level=request.difficulty,
        passed=int(level) >= int(request.difficulty),
        pushed=request.pushed,
    )

