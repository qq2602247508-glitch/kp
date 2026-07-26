from dataclasses import dataclass

CORE_PACK_ID = "coc7e.core.zh-v1.2.1"
CORE_FILENAME = "COC7th核心规则书v1.2.1.pdf"
CORE_CHECKSUM = "22f5f56b7a0989cbded695d39c7d5eddddd809cfc9d2c47e4cf4c5d7edea6815"


@dataclass(frozen=True)
class EngineCitation:
    citation_id: str
    source_pack_id: str
    filename: str
    page: int
    section: str
    edition: str = "7e"
    module: str = "core"
    era: tuple[str, ...] = ()
    checksum: str = CORE_CHECKSUM

    def as_dict(self) -> dict[str, str | int | list[str]]:
        return {
            "citation_id": self.citation_id,
            "source_pack_id": self.source_pack_id,
            "filename": self.filename,
            "page": self.page,
            "section": self.section,
            "edition": self.edition,
            "module": self.module,
            "era": list(self.era),
            "checksum": self.checksum,
        }


SANITY_CITATION = EngineCitation(
    citation_id="0d626519-a343-5a71-998c-9b0b56f76232",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=367,
    section="第十六章附录/理智规则摘要",
)
INJURY_CITATION = EngineCitation(
    citation_id="898d81fc-963c-5473-9f7c-4d99e65d4d4b",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=103,
    section="第六章战斗/昏迷重伤濒死",
)
RECOVERY_CITATION = EngineCitation(
    citation_id="0e24f8d1-eacb-54b6-b784-6aa1db5421f4",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=104,
    section="重伤恢复",
)
RECOVERY_CONTEXT_CITATION = EngineCitation(
    citation_id="b87f9a5c-fd66-5cf8-b681-86677258aabe",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=104,
    section="急救与医学",
)
COMBAT_CITATION = EngineCitation(
    citation_id="69bcc3eb-67af-5d76-8e42-005fbbfc8358",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=89,
    section="武器战斗示例",
)
SKILL_IMPROVEMENT_CITATION = EngineCitation(
    citation_id="8a7eeb90-2d50-5cc8-a5d2-dba85ca6b3dc",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=79,
    section="第五章游戏系统/经验奖励：幕间成长",
)
MELEE_WEAPON_CITATION = EngineCitation(
    citation_id="2ce1026d-07ef-5146-a22a-58cf4f9f9c17",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=352,
    section="武器表（近战）",
)
HANDGUN_WEAPON_CITATION = EngineCitation(
    citation_id="3ea627e3-523b-5567-8460-3c33b84cdc9e",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=353,
    section="武器表（手枪）",
)
SHOTGUN_WEAPON_CITATION = EngineCitation(
    citation_id="80b6fe46-fdf9-50b5-8227-73b7756f293a",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=354,
    section="武器表（霰弹枪）",
)
CHASE_MOV_CITATION = EngineCitation(
    citation_id="b5ac21aa-0b22-50a2-848d-ba61e674c993",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=116,
    section="追逐中的MOV与行动点",
)
CHASE_ACTIONS_CITATION = EngineCitation(
    citation_id="eeb778d6-5e69-5af7-9f38-511c5f4827a7",
    source_pack_id=CORE_PACK_ID, filename=CORE_FILENAME, page=117, section="追逐行动",
)
CHASE_HAZARDS_CITATION = EngineCitation(
    citation_id="2b7817b9-a2da-5ba9-8315-c10421bca87d",
    source_pack_id=CORE_PACK_ID, filename=CORE_FILENAME, page=118, section="追逐危害",
)
CHASE_BARRIERS_CITATION = EngineCitation(
    citation_id="28bb7282-3718-5ddc-b91a-3e5eca7bca05",
    source_pack_id=CORE_PACK_ID, filename=CORE_FILENAME, page=119, section="追逐障碍",
)
CHASE_CITATIONS = (CHASE_MOV_CITATION, CHASE_ACTIONS_CITATION)


@dataclass(frozen=True)
class WeaponPolicy:
    weapon_key: str
    name: str
    damage_notation: str
    maximum_rolled_damage: int
    skill_key: str
    uses_damage_bonus: bool
    citations: tuple[EngineCitation, ...]

    @property
    def citation(self) -> EngineCitation:
        return self.citations[0]


WEAPONS: tuple[WeaponPolicy, ...] = (
    WeaponPolicy(
        "unarmed",
        "徒手格斗",
        "1D3+DB",
        3,
        "fighting_brawl",
        True,
        (MELEE_WEAPON_CITATION,),
    ),
    WeaponPolicy(
        "knife_small",
        "小刀",
        "1D4+DB",
        4,
        "fighting_brawl",
        True,
        (MELEE_WEAPON_CITATION,),
    ),
    WeaponPolicy(
        "club",
        "棍棒",
        "1D6+DB",
        6,
        "fighting_brawl",
        True,
        (MELEE_WEAPON_CITATION,),
    ),
    WeaponPolicy(
        "handgun_38",
        ".38 左轮手枪",
        "1D10",
        10,
        "firearms_handgun",
        False,
        (HANDGUN_WEAPON_CITATION,),
    ),
    WeaponPolicy(
        "shotgun_12g",
        "12 号霰弹枪",
        "4D6/2D6/1D6",
        24,
        "firearms_rifle_shotgun",
        False,
        (SHOTGUN_WEAPON_CITATION,),
    ),
)
WEAPON_BY_KEY = {weapon.weapon_key: weapon for weapon in WEAPONS}


def sanity_conditions(
    *,
    starting_sanity: int,
    single_loss: int,
    session_loss: int,
    intelligence_check_passed: bool | None,
    existing: set[str],
) -> set[str]:
    result = set(existing)
    if single_loss >= 5 and intelligence_check_passed:
        result.add("temporary_insanity")
    if session_loss >= max(1, (starting_sanity + 4) // 5):
        result.add("indefinite_insanity")
    return result


def injury_state(
    *,
    hit_points: int,
    maximum_hit_points: int,
    damage: int,
    existing: set[str],
) -> tuple[int, set[str]]:
    next_hit_points = max(0, hit_points - damage)
    result = set(existing)
    major_wound = damage >= max(1, (maximum_hit_points + 1) // 2)
    if major_wound:
        result.add("major_wound")
    if next_hit_points == 0:
        result.add("unconscious")
        if "major_wound" in result:
            result.add("dying")
    return next_hit_points, result


def recovery_amount(care_type: str, healing_roll: int | None) -> int:
    if care_type == "first_aid":
        return 1
    if care_type in {"medicine", "natural"}:
        if healing_roll is None or not 1 <= healing_roll <= 3:
            raise ValueError("medicine and natural recovery require a 1-3 healing roll")
        return healing_roll
    raise ValueError("unsupported care type")


def skill_improvement(
    *, current_value: int, improvement_roll: int, increase_roll: int | None
) -> tuple[int, bool, int]:
    """Resolve one marked COC7 skill check with caller-supplied dice."""
    if not 0 <= current_value <= 999:
        raise ValueError("current skill value must be between 0 and 999")
    if not 1 <= improvement_roll <= 100:
        raise ValueError("improvement roll must be between 1 and 100")
    improved = improvement_roll > current_value or improvement_roll > 95
    if improved:
        if increase_roll is None or not 1 <= increase_roll <= 10:
            raise ValueError("a successful improvement check requires a 1D10 result")
        return current_value + increase_roll, True, increase_roll
    if increase_roll is not None:
        raise ValueError("a failed improvement check must not include a 1D10 result")
    return current_value, False, 0
