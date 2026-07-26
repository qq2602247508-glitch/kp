from uuid import uuid4

import pytest
from pydantic import ValidationError

from coc_kp_assistant.domain import (
    CoreCharacteristics,
    InvestigatorBackstory,
    InvestigatorCreate,
    InvestigatorState,
    SkillEntry,
)


def sample_profile() -> InvestigatorCreate:
    return InvestigatorCreate(
        name="林雾",
        player_name="测试玩家",
        occupation="记者",
        age=29,
        characteristics=CoreCharacteristics(
            strength=50,
            constitution=60,
            size=50,
            dexterity=70,
            appearance=55,
            intelligence=75,
            power=65,
            education=80,
        ),
        luck=55,
        move_rate=8,
        skills=(
            SkillEntry(
                skill_key="library_use",
                display_name="图书馆使用",
                base_value=20,
                current_value=65,
            ),
        ),
        backstory=InvestigatorBackstory(
            ideology_and_beliefs=("真相值得付出代价",),
            significant_people=("导师周先生",),
        ),
    )


def test_profile_derives_coc7_resource_limits_and_skill_thresholds() -> None:
    profile = sample_profile()

    assert profile.maximum_hit_points == 11
    assert profile.maximum_magic_points == 13
    assert profile.starting_sanity == 65
    assert profile.skills[0].half_value == 32
    assert profile.skills[0].fifth_value == 13


def test_state_enforces_mythos_adjusted_sanity_cap() -> None:
    profile = sample_profile()

    with pytest.raises(ValidationError, match="mythos-adjusted cap"):
        InvestigatorState(
            investigator_id=uuid4(),
            campaign_id=uuid4(),
            profile=profile,
            hit_points=11,
            magic_points=13,
            sanity=95,
            mythos=10,
        )


def test_skill_specializations_must_be_unique() -> None:
    profile = sample_profile()
    duplicate = profile.skills[0]
    payload = profile.model_dump()
    payload["skills"] = [duplicate.model_dump(), duplicate.model_dump()]

    with pytest.raises(ValidationError, match="must be unique"):
        InvestigatorCreate.model_validate(payload)
