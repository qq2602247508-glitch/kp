from pathlib import Path

FORBIDDEN_PRODUCTION_TOKENS = (
    "armor_class",
    "challenge_rating",
    "class_level",
    "death_save",
    "proficiency_bonus",
    "saving_throw",
    "short_rest",
    "spell_slot",
)


def test_production_package_has_no_foreign_ruleset_tokens() -> None:
    source_root = Path(__file__).parents[1] / "src" / "coc_kp_assistant"
    production_text = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in source_root.rglob("*.py")
    )

    found = [token for token in FORBIDDEN_PRODUCTION_TOKENS if token in production_text]
    assert found == []


def test_production_package_never_imports_previous_project() -> None:
    source_root = Path(__file__).parents[1] / "src" / "coc_kp_assistant"
    imports = "\n".join(
        line
        for path in source_root.rglob("*.py")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(("from ", "import "))
    )

    previous_package = "dnd" + "_dm_assistant"
    assert previous_package not in imports.lower()

