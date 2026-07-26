import json
from pathlib import Path

import httpx
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from coc_kp_assistant.rag import (
    COLLECTION_NAME,
    ChunkMetadata,
    IndexIncompleteError,
    OllamaEmbeddingProvider,
    QdrantLocalVectorIndex,
    RuleChunk,
    VectorPoint,
)


def _chunk(
    chunk_id: str,
    *,
    pack_id: str,
    enabled_by_default: bool,
    legacy: bool = False,
) -> RuleChunk:
    return RuleChunk(
        chunk_id=chunk_id,
        text=f"Text for {pack_id}",
        metadata=ChunkMetadata(
            source_pack=pack_id,
            edition="7e",
            tier="legacy" if legacy else ("core" if enabled_by_default else "optional"),
            module="legacy" if legacy else ("core" if enabled_by_default else "magic"),
            era=(),
            filename=f"{pack_id}.pdf",
            page=1,
            section="Rules",
            checksum=("a" if enabled_by_default else "b") * 64,
            enabled_by_default=enabled_by_default,
            legacy=legacy,
        ),
    )


def test_ollama_adapter_calls_only_embed_with_the_installed_model() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "model": "bge-m3:latest",
                "embeddings": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    provider = OllamaEmbeddingProvider(client=client, dimension=3)

    vectors = provider.embed(["first", "second"])

    assert vectors == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert requests == [
        (
            "/api/embed",
            {
                "input": ["first", "second"],
                "model": "bge-m3:latest",
                "truncate": False,
            },
        )
    ]


def test_ollama_adapter_batches_large_corpora_without_changing_order() -> None:
    request_inputs: list[list[str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        request_inputs.append(inputs)
        return httpx.Response(
            200,
            json={
                "model": "bge-m3:latest",
                "embeddings": [[float(len(text)), 0.0] for text in inputs],
            },
        )

    provider = OllamaEmbeddingProvider(
        client=httpx.Client(transport=httpx.MockTransport(respond)),
        dimension=2,
        batch_size=2,
    )

    vectors = provider.embed(["a", "bb", "ccc"])

    assert request_inputs == [["a", "bb"], ["ccc"]]
    assert vectors == [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]


def test_qdrant_local_adapter_persists_points_filters_packs_and_deletes_by_pack(
    tmp_path: Path,
) -> None:
    path = tmp_path / "coc7-qdrant"
    index = QdrantLocalVectorIndex(path=path)
    core = _chunk(
        "6574a869-50df-5f2c-8ee0-f69f95af4374",
        pack_id="coc7e.core.test",
        enabled_by_default=True,
    )
    optional = _chunk(
        "a87d1bdb-6eca-5132-9b95-5640ff0e9a31",
        pack_id="coc7e.magic.test",
        enabled_by_default=False,
    )
    legacy = _chunk(
        "24085269-7a4f-5d93-87aa-5930e36b15cd",
        pack_id="coc-classic.legacy.test",
        enabled_by_default=False,
        legacy=True,
    )

    assert index.collection_name == COLLECTION_NAME
    assert index.state().exists is False
    index.prepare(3)
    index.set_corpus_digest("d" * 64)
    index.upsert(
        [
            VectorPoint(core, [1.0, 0.0, 0.0]),
            VectorPoint(optional, [0.9, 0.1, 0.0]),
            VectorPoint(legacy, [0.8, 0.2, 0.0]),
        ]
    )

    hits = index.search(
        [1.0, 0.0, 0.0], allowed_pack_ids={"coc7e.core.test"}, limit=10
    )
    assert [(hit.chunk.chunk_id, hit.chunk.metadata.as_payload()) for hit in hits] == [
        (core.chunk_id, core.metadata.as_payload())
    ]
    assert index.state().point_count == 3
    assert index.state().corpus_digest == "d" * 64

    index.delete_packs({"coc7e.magic.test"})

    assert index.state().point_count == 2
    index.close()


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("enabled_by_default", None),
        ("enabled_by_default", "true"),
        ("legacy", None),
        ("legacy", 0),
    ],
)
def test_qdrant_adapter_rejects_missing_or_non_boolean_filter_metadata(
    tmp_path: Path, field: str, bad_value: object
) -> None:
    path = tmp_path / f"invalid-{field}-{type(bad_value).__name__}"
    chunk = _chunk(
        "6574a869-50df-5f2c-8ee0-f69f95af4374",
        pack_id="coc7e.core.test",
        enabled_by_default=True,
    )
    payload = {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        **chunk.metadata.as_payload(),
    }
    if bad_value is None:
        del payload[field]
    else:
        payload[field] = bad_value
    index = QdrantLocalVectorIndex(path=path)
    index.prepare(3)
    index.close()
    raw_client = QdrantClient(path=str(path))
    raw_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            qdrant_models.PointStruct(
                id=chunk.chunk_id,
                vector=[1.0, 0.0, 0.0],
                payload=payload,
            )
        ],
        wait=True,
    )
    raw_client.close()
    index = QdrantLocalVectorIndex(path=path)

    with pytest.raises(IndexIncompleteError, match=field):
        index.search(
            [1.0, 0.0, 0.0],
            allowed_pack_ids={"coc7e.core.test"},
            limit=1,
        )

    index.close()
