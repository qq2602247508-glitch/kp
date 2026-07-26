from dataclasses import dataclass

CORE_PACK_ID = "coc7e.core.zh-v1.2.1"
CORE_FILENAME = "COC7th核心规则书v1.2.1.pdf"


@dataclass(frozen=True)
class EngineCitation:
    citation_id: str
    source_pack_id: str
    filename: str
    page: int
    section: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "citation_id": self.citation_id,
            "source_pack_id": self.source_pack_id,
            "filename": self.filename,
            "page": self.page,
            "section": self.section,
        }


SANITY_CITATION = EngineCitation(
    citation_id="coc7e.core.sanity-loss-and-insanity",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=367,
    section="第十六章附录／理智规则摘要",
)
INJURY_CITATION = EngineCitation(
    citation_id="coc7e.core.damage-major-wounds-and-dying",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=103,
    section="第六章战斗／伤害、重伤、昏迷与濒死",
)
RECOVERY_CITATION = EngineCitation(
    citation_id="coc7e.core.healing-and-recovery",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=104,
    section="第六章战斗／急救、医学与恢复",
)
COMBAT_CITATION = EngineCitation(
    citation_id="coc7e.core.combat-and-damage",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=89,
    section="第六章战斗／格斗攻击与伤害",
)
MELEE_WEAPON_CITATION = EngineCitation(
    citation_id="coc7e.core.weapon-table-melee",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=352,
    section="第十六章附录／武器表（格斗武器）",
)
HANDGUN_WEAPON_CITATION = EngineCitation(
    citation_id="coc7e.core.weapon-table-handguns",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=353,
    section="第十六章附录／武器表（手枪）",
)
SHOTGUN_WEAPON_CITATION = EngineCitation(
    citation_id="coc7e.core.weapon-table-shotguns",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=354,
    section="第十六章附录／武器表（霰弹枪）",
)
CHASE_CITATION = EngineCitation(
    citation_id="coc7e.core.chases-movement-actions",
    source_pack_id=CORE_PACK_ID,
    filename=CORE_FILENAME,
    page=119,
    section="第七章追逐／移动行动",
)


@dataclass(frozen=True)
class WeaponPolicy:
    weapon_key: str
    name: str
    damage_notation: str
    maximum_rolled_damage: int
    skill_key: str
    uses_damage_bonus: bool
    citation: EngineCitation


WEAPONS: tuple[WeaponPolicy, ...] = (
    WeaponPolicy(
        "unarmed",
        "徒手格斗",
        "1D3+DB",
        3,
        "fighting_brawl",
        True,
        MELEE_WEAPON_CITATION,
    ),
    WeaponPolicy(
        "knife_small",
        "小刀",
        "1D4+DB",
        4,
        "fighting_brawl",
        True,
        MELEE_WEAPON_CITATION,
    ),
    WeaponPolicy(
        "club",
        "棍棒",
        "1D6+DB",
        6,
        "fighting_brawl",
        True,
        MELEE_WEAPON_CITATION,
    ),
    WeaponPolicy(
        "handgun_38",
        ".38 左轮手枪",
        "1D10",
        10,
        "firearms_handgun",
        False,
        HANDGUN_WEAPON_CITATION,
    ),
    WeaponPolicy(
        "shotgun_12g",
        "12 号霰弹枪",
        "4D6/2D6/1D6",
        24,
        "firearms_rifle_shotgun",
        False,
        SHOTGUN_WEAPON_CITATION,
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
    if session_loss >= max(1, starting_sanity // 5):
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
