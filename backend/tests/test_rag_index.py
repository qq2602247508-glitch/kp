import json
from copy import deepcopy
from pathlib import Path

import pytest

from coc_kp_assistant.rag import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    PRODUCT_NAMESPACE,
    RULESET_NAMESPACE,
    CollectionState,
    Corpus,
    IndexCompatibilityError,
    IndexIncompleteError,
    RagIndexer,
    RagSearcher,
    SearchHit,
    SearchOptions,
    VectorPoint,
)


def _record(
    pack_id: str,
    *,
    text: str,
    checksum: str,
    kind: str,
    default_enabled: bool,
) -> dict[str, object]:
    provenance = {
        "edition": "7e",
        "eras": [],
        "filename": f"{pack_id}.pdf",
        "format": "pdf",
        "locator": "source",
        "module": kind,
        "sha256": checksum,
        "source_pack": pack_id,
        "source_path": f"/read-only/{pack_id}.pdf",
    }
    return {
        "content": {
            "pages": [
                {
                    "page_number": 1,
                    "provenance": {
                        key: value for key, value in provenance.items() if key != "source_path"
                    }
                    | {"locator": "page:1"},
                    "text": text,
                }
            ]
        },
        "default_enabled": default_enabled,
        "edition": "7e",
        "kind": kind,
        "pack_id": pack_id,
        "provenance": provenance,
        "ruleset": "coc7e",
        "title": pack_id,
        "version": "test",
    }


def _corpus(*records: dict[str, object]) -> Corpus:
    return Corpus(PRODUCT_NAMESPACE, RULESET_NAMESPACE, records)


class _DeterministicEmbedder:
    model_name = EMBEDDING_MODEL
    dimension = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.5] for text in texts]


class _MemoryVectorIndex:
    collection_name = COLLECTION_NAME

    def __init__(self) -> None:
        self.vector_size: int | None = None
        self.corpus_digest: str | None = None
        self.points: dict[str, VectorPoint] = {}

    def state(self) -> CollectionState:
        return CollectionState(
            exists=self.vector_size is not None,
            vector_size=self.vector_size,
            point_count=len(self.points),
            corpus_digest=self.corpus_digest,
        )

    def prepare(self, vector_size: int, *, recreate: bool = False) -> None:
        if recreate:
            self.points.clear()
            self.corpus_digest = None
        if self.vector_size not in (None, vector_size):
            raise ValueError("wrong vector size")
        self.vector_size = vector_size

    def delete_packs(self, pack_ids: set[str]) -> None:
        self.points = {
            point_id: point
            for point_id, point in self.points.items()
            if point.chunk.metadata.source_pack not in pack_ids
        }

    def upsert(self, points: list[VectorPoint]) -> None:
        self.points.update({point.chunk.chunk_id: point for point in points})

    def set_corpus_digest(self, corpus_digest: str) -> None:
        self.corpus_digest = corpus_digest

    def search(
        self, vector: list[float], *, allowed_pack_ids: set[str], limit: int
    ) -> list[SearchHit]:
        del vector
        matches = [
            SearchHit(chunk=point.chunk, score=1.0)
            for point in self.points.values()
            if point.chunk.metadata.source_pack in allowed_pack_ids
        ]
        return sorted(matches, key=lambda hit: hit.chunk.chunk_id)[:limit]


def test_incremental_build_embeds_only_changed_packs_and_removes_deleted_packs(
    tmp_path: Path,
) -> None:
    core = _record(
        "coc7e.core.test",
        text="# Skills\nCore skill rules.",
        checksum="a" * 64,
        kind="core",
        default_enabled=True,
    )
    optional = _record(
        "coc7e.magic.test",
        text="# Spells\nOptional spell rules.",
        checksum="b" * 64,
        kind="magic",
        default_enabled=False,
    )
    index = _MemoryVectorIndex()
    indexer = RagIndexer(
        embedder=_DeterministicEmbedder(),
        vector_index=index,
        manifest_path=tmp_path / "index-manifest.json",
    )

    initial = indexer.build(_corpus(core, optional))
    unchanged = indexer.build(_corpus(core, optional))
    changed_optional = _record(
        "coc7e.magic.test",
        text="# Spells\nChanged optional spell rules.",
        checksum="c" * 64,
        kind="magic",
        default_enabled=False,
    )
    incremental = indexer.build(_corpus(core, changed_optional))
    removed = indexer.build(_corpus(core))

    assert initial.embedded_chunk_count == 2
    assert unchanged.embedded_chunk_count == 0
    assert unchanged.skipped_pack_count == 2
    assert incremental.embedded_chunk_count == 1
    assert incremental.deleted_pack_ids == ("coc7e.magic.test",)
    assert removed.embedded_chunk_count == 0
    assert removed.deleted_pack_ids == ("coc7e.magic.test",)
    assert index.state().point_count == 1
    manifest = json.loads((tmp_path / "index-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["chunk_count"] == 1
    assert manifest["collection"] == "coc7_rules"
    assert manifest["embedding"]["model"] == "bge-m3:latest"
    assert manifest["packs"]["coc7e.core.test"]["checksum"] == "a" * 64


def test_renaming_a_source_replaces_stale_filename_metadata(tmp_path: Path) -> None:
    core = _record(
        "coc7e.core.test",
        text="# Skills\nCore skill rules.",
        checksum="a" * 64,
        kind="core",
        default_enabled=True,
    )
    index = _MemoryVectorIndex()
    indexer = RagIndexer(
        embedder=_DeterministicEmbedder(),
        vector_index=index,
        manifest_path=tmp_path / "index-manifest.json",
    )
    indexer.build(_corpus(core))
    original_chunk_id = next(iter(index.points))
    renamed = deepcopy(core)
    renamed["provenance"]["filename"] = "renamed-core.pdf"  # type: ignore[index]
    renamed["content"]["pages"][0]["provenance"]["filename"] = "renamed-core.pdf"  # type: ignore[index]

    result = indexer.build(_corpus(renamed))

    assert result.embedded_chunk_count == 1
    assert result.deleted_pack_ids == ("coc7e.core.test",)
    assert len(index.points) == 1
    replacement = next(iter(index.points.values())).chunk
    assert replacement.chunk_id != original_chunk_id
    assert replacement.metadata.filename == "renamed-core.pdf"


def test_build_leaves_incomplete_manifest_when_vector_count_does_not_match(
    tmp_path: Path,
) -> None:
    class _DroppingIndex(_MemoryVectorIndex):
        def upsert(self, points: list[VectorPoint]) -> None:
            del points

    indexer = RagIndexer(
        embedder=_DeterministicEmbedder(),
        vector_index=_DroppingIndex(),
        manifest_path=tmp_path / "index-manifest.json",
    )
    core = _record(
        "coc7e.core.test",
        text="# Skills\nCore skill rules.",
        checksum="a" * 64,
        kind="core",
        default_enabled=True,
    )

    with pytest.raises(IndexIncompleteError, match="point count"):
        indexer.build(_corpus(core))

    manifest = json.loads((tmp_path / "index-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "building"


def test_mismatched_existing_manifest_is_rejected_before_index_changes(tmp_path: Path) -> None:
    manifest_path = tmp_path / "index-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "product": "foreign-assistant",
                "ruleset": "coc7e",
                "collection": "coc7_rules",
                "status": "complete",
                "chunker": {
                    "name": "coc7-heading-page",
                    "version": 1,
                    "config": {"max_chars": 1200},
                },
                "embedding": {"model": "bge-m3:latest", "dimension": 3},
                "chunk_count": 0,
                "corpus_digest": "0" * 64,
                "packs": {},
            }
        ),
        encoding="utf-8",
    )
    index = _MemoryVectorIndex()
    indexer = RagIndexer(
        embedder=_DeterministicEmbedder(),
        vector_index=index,
        manifest_path=manifest_path,
    )

    with pytest.raises(IndexCompatibilityError, match="product"):
        indexer.build(_corpus())

    assert index.state().exists is False


@pytest.mark.parametrize(
    "mutation",
    ["wrong_chunker", "wrong_corpus_digest", "missing_pack_chunk_digest"],
)
def test_search_rejects_malformed_manifest_identity(
    tmp_path: Path, mutation: str
) -> None:
    core = _record(
        "coc7e.core.test",
        text="# Skills\nCore skill rules.",
        checksum="a" * 64,
        kind="core",
        default_enabled=True,
    )
    index = _MemoryVectorIndex()
    manifest_path = tmp_path / "index-manifest.json"
    embedder = _DeterministicEmbedder()
    RagIndexer(embedder=embedder, vector_index=index, manifest_path=manifest_path).build(
        _corpus(core)
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "wrong_chunker":
        manifest["chunker"] = {
            "name": "foreign-chunker",
            "version": 1,
            "config": {"max_chars": 1200},
        }
    elif mutation == "wrong_corpus_digest":
        manifest["corpus_digest"] = "f" * 64
    else:
        del manifest["packs"]["coc7e.core.test"]["chunk_digest"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    searcher = RagSearcher(
        embedder=embedder,
        vector_index=index,
        manifest_path=manifest_path,
    )

    with pytest.raises(IndexCompatibilityError, match="chunker|corpus|chunk digest"):
        searcher.search("skill")


def test_search_rejects_a_same_namespace_manifest_for_a_different_corpus(
    tmp_path: Path,
) -> None:
    pack_id = "coc7e.core.zh-v1.2.1"
    original_corpus = _corpus(
        _record(
            pack_id,
            text="# Skills\nOriginal skill rules.",
            checksum="a" * 64,
            kind="core",
            default_enabled=True,
        )
    )
    other_corpus = _corpus(
        _record(
            pack_id,
            text="# Skills\nDifferent rules with the same source checksum.",
            checksum="a" * 64,
            kind="core",
            default_enabled=True,
        )
    )
    embedder = _DeterministicEmbedder()
    original_index = _MemoryVectorIndex()
    original_manifest = tmp_path / "original-manifest.json"
    RagIndexer(
        embedder=embedder,
        vector_index=original_index,
        manifest_path=original_manifest,
    ).build(original_corpus)
    other_manifest = tmp_path / "other-manifest.json"
    RagIndexer(
        embedder=embedder,
        vector_index=_MemoryVectorIndex(),
        manifest_path=other_manifest,
    ).build(other_corpus)
    original_manifest.write_bytes(other_manifest.read_bytes())
    searcher = RagSearcher(
        embedder=embedder,
        vector_index=original_index,
        manifest_path=original_manifest,
    )

    with pytest.raises(IndexCompatibilityError, match="corpus"):
        searcher.search("skill")


def test_search_fails_closed_for_incomplete_manifest_or_collection_state(
    tmp_path: Path,
) -> None:
    core = _record(
        "coc7e.core.test",
        text="# Skills\nCore skill rules.",
        checksum="a" * 64,
        kind="core",
        default_enabled=True,
    )
    index = _MemoryVectorIndex()
    manifest_path = tmp_path / "index-manifest.json"
    indexer = RagIndexer(
        embedder=_DeterministicEmbedder(),
        vector_index=index,
        manifest_path=manifest_path,
    )
    indexer.build(_corpus(core))
    searcher = RagSearcher(
        embedder=_DeterministicEmbedder(),
        vector_index=index,
        manifest_path=manifest_path,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "building"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(IndexIncompleteError, match="complete"):
        searcher.search("skill")

    manifest["status"] = "complete"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    index.points.clear()
    with pytest.raises(IndexIncompleteError, match="point count"):
        searcher.search("skill")


def test_search_excludes_optional_and_legacy_packs_until_each_is_explicitly_enabled(
    tmp_path: Path,
) -> None:
    records = (
        _record(
            "coc7e.core.zh-v1.2.1",
            text="# Skills\nCore.",
            checksum="a" * 64,
            kind="core",
            default_enabled=True,
        ),
        _record(
            "coc7e.magic.test",
            text="# Magic\nOptional.",
            checksum="b" * 64,
            kind="magic",
            default_enabled=False,
        ),
        _record(
            "coc-classic.legacy.test",
            text="# Classic\nLegacy.",
            checksum="c" * 64,
            kind="legacy",
            default_enabled=False,
        ),
    )
    index = _MemoryVectorIndex()
    manifest_path = tmp_path / "index-manifest.json"
    embedder = _DeterministicEmbedder()
    RagIndexer(
        embedder=embedder,
        vector_index=index,
        manifest_path=manifest_path,
    ).build(_corpus(*records))
    searcher = RagSearcher(
        embedder=embedder,
        vector_index=index,
        manifest_path=manifest_path,
    )

    defaults = searcher.search("rules")
    optional = searcher.search(
        "rules", options=SearchOptions(enabled_pack_ids=("coc7e.magic.test",))
    )
    legacy = searcher.search(
        "rules", options=SearchOptions(enabled_pack_ids=("coc-classic.legacy.test",))
    )

    assert [hit.chunk.metadata.source_pack for hit in defaults] == [
        "coc7e.core.zh-v1.2.1"
    ]
    assert {hit.chunk.metadata.source_pack for hit in optional} == {
        "coc7e.core.zh-v1.2.1",
        "coc7e.magic.test",
    }
    assert {hit.chunk.metadata.source_pack for hit in legacy} == {
        "coc7e.core.zh-v1.2.1",
        "coc-classic.legacy.test",
    }


def test_search_defaults_allow_only_approved_core_and_p1_even_if_optional_is_marked_default(
    tmp_path: Path,
) -> None:
    records = (
        _record(
            "coc7e.core.zh-v1.2.1",
            text="# Core\nCore.",
            checksum="a" * 64,
            kind="core",
            default_enabled=True,
        ),
        _record(
            "coc7e.investigator-handbook.zh-v1.21",
            text="# Investigator\nP1.",
            checksum="b" * 64,
            kind="investigator",
            default_enabled=True,
        ),
        _record(
            "coc7e.magic.test",
            text="# Magic\nOptional.",
            checksum="c" * 64,
            kind="magic",
            default_enabled=True,
        ),
        _record(
            "coc7e.quickstart.test",
            text="# Quickstart\nOptional.",
            checksum="d" * 64,
            kind="quickstart",
            default_enabled=True,
        ),
    )
    corpus = _corpus(*records)
    index = _MemoryVectorIndex()
    manifest_path = tmp_path / "index-manifest.json"
    embedder = _DeterministicEmbedder()
    RagIndexer(embedder=embedder, vector_index=index, manifest_path=manifest_path).build(
        corpus
    )
    searcher = RagSearcher(
        embedder=embedder,
        vector_index=index,
        manifest_path=manifest_path,
    )

    defaults = searcher.search("rules")
    with_magic = searcher.search(
        "rules", options=SearchOptions(enabled_pack_ids=("coc7e.magic.test",))
    )

    assert {hit.chunk.metadata.source_pack for hit in defaults} == {
        "coc7e.core.zh-v1.2.1",
        "coc7e.investigator-handbook.zh-v1.21",
    }
    assert {hit.chunk.metadata.source_pack for hit in with_magic} == {
        "coc7e.core.zh-v1.2.1",
        "coc7e.investigator-handbook.zh-v1.21",
        "coc7e.magic.test",
    }


def test_search_rejects_an_unindexed_pack_instead_of_weakening_filters(tmp_path: Path) -> None:
    core = _record(
        "coc7e.core.test",
        text="# Skills\nCore.",
        checksum="a" * 64,
        kind="core",
        default_enabled=True,
    )
    index = _MemoryVectorIndex()
    manifest_path = tmp_path / "index-manifest.json"
    embedder = _DeterministicEmbedder()
    RagIndexer(embedder=embedder, vector_index=index, manifest_path=manifest_path).build(
        _corpus(core)
    )
    searcher = RagSearcher(
        embedder=embedder,
        vector_index=index,
        manifest_path=manifest_path,
    )

    with pytest.raises(IndexCompatibilityError, match="not indexed"):
        searcher.search(
            "rules", options=SearchOptions(enabled_pack_ids=("coc7e.unknown.test",))
        )
