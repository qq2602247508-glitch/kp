from copy import deepcopy

import pytest

from coc_kp_assistant.rag import (
    PRODUCT_NAMESPACE,
    RULESET_NAMESPACE,
    Corpus,
    chunk_corpus,
)


def _record(
    *,
    pack_id: str = "coc7e.core.test",
    kind: str = "core",
    default_enabled: bool = True,
) -> dict[str, object]:
    checksum = "a" * 64
    provenance = {
        "edition": "7e",
        "eras": ["1920s"],
        "filename": "core-test.pdf",
        "format": "pdf",
        "locator": "source",
        "module": kind,
        "sha256": checksum,
        "source_pack": pack_id,
        "source_path": "/read-only/core-test.pdf",
    }
    return {
        "content": {
            "pages": [
                {
                    "page_number": 12,
                    "provenance": {
                        key: value for key, value in provenance.items() if key != "source_path"
                    }
                    | {"locator": "page:12"},
                    "text": (
                        "# Combat\n"
                        "Attacks are resolved with opposed skill rolls.\n\n"
                        "## Damage\n"
                        "Damage is applied after a successful attack."
                    ),
                },
                {
                    "page_number": 13,
                    "provenance": {
                        key: value for key, value in provenance.items() if key != "source_path"
                    }
                    | {"locator": "page:13"},
                    "text": "# Chases\nA chase begins when one party flees.",
                },
            ]
        },
        "default_enabled": default_enabled,
        "edition": "7e",
        "kind": kind,
        "pack_id": pack_id,
        "provenance": provenance,
        "ruleset": "coc7e",
        "title": "Core Test",
        "version": "test",
    }


def test_heading_and_page_aware_chunks_have_stable_ids_and_complete_metadata() -> None:
    corpus = Corpus(
        product=PRODUCT_NAMESPACE,
        ruleset=RULESET_NAMESPACE,
        records=(_record(),),
    )

    first = chunk_corpus(corpus, max_chars=80)
    second = chunk_corpus(corpus, max_chars=80)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert len(set(chunk.chunk_id for chunk in first)) == len(first)
    assert [(chunk.metadata.page, chunk.metadata.section) for chunk in first] == [
        (12, "Combat"),
        (12, "Damage"),
        (13, "Chases"),
    ]
    assert first[0].text == "Combat\nAttacks are resolved with opposed skill rolls."
    assert first[0].metadata.as_payload() == {
        "checksum": "a" * 64,
        "edition": "7e",
        "enabled_by_default": True,
        "era": ["1920s"],
        "filename": "core-test.pdf",
        "legacy": False,
        "module": "core",
        "page": 12,
        "section": "Combat",
        "source_pack": "coc7e.core.test",
        "tier": "core",
    }


def test_editing_one_page_changes_only_that_pages_chunk_ids() -> None:
    original = Corpus(PRODUCT_NAMESPACE, RULESET_NAMESPACE, (_record(),))
    changed_record = deepcopy(_record())
    changed_record["content"]["pages"][1]["text"] += " Fast movement matters."  # type: ignore[index]
    changed_record["provenance"]["sha256"] = "b" * 64  # type: ignore[index]
    for page in changed_record["content"]["pages"]:  # type: ignore[index]
        page["provenance"]["sha256"] = "b" * 64
    changed = Corpus(PRODUCT_NAMESPACE, RULESET_NAMESPACE, (changed_record,))

    original_chunks = chunk_corpus(original, max_chars=80)
    changed_chunks = chunk_corpus(changed, max_chars=80)

    assert [chunk.chunk_id for chunk in original_chunks if chunk.metadata.page == 12] == [
        chunk.chunk_id for chunk in changed_chunks if chunk.metadata.page == 12
    ]
    assert [chunk.chunk_id for chunk in original_chunks if chunk.metadata.page == 13] != [
        chunk.chunk_id for chunk in changed_chunks if chunk.metadata.page == 13
    ]


def test_repeated_identical_headings_in_one_source_unit_get_unique_ids() -> None:
    record = _record()
    record["content"]["pages"][0]["text"] = (  # type: ignore[index]
        "# Repeated\nSame text.\n\n# Repeated\nSame text."
    )
    record["content"]["pages"] = record["content"]["pages"][:1]  # type: ignore[index]

    chunks = chunk_corpus(
        Corpus(PRODUCT_NAMESPACE, RULESET_NAMESPACE, (record,)),
        max_chars=80,
    )

    assert len(chunks) == 2
    assert len({chunk.chunk_id for chunk in chunks}) == 2


@pytest.mark.parametrize(
    ("product", "ruleset"),
    [
        ("foreign-assistant", "coc7e"),
        ("local-coc-kp-assistant", "foreign7e"),
    ],
)
def test_corpus_refuses_non_coc_product_or_ruleset(product: str, ruleset: str) -> None:
    with pytest.raises(ValueError, match="COC"):
        Corpus(product=product, ruleset=ruleset, records=(_record(),))


def test_corpus_refuses_a_record_with_a_mismatched_ruleset() -> None:
    record = _record()
    record["ruleset"] = "foreign7e"

    with pytest.raises(ValueError, match="record ruleset"):
        Corpus(PRODUCT_NAMESPACE, RULESET_NAMESPACE, (record,))
