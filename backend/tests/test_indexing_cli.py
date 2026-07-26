import json
from pathlib import Path

import pytest

from coc_kp_assistant import indexing


class FakeEmbedder:
    def __init__(self, *, base_url: str):
        self.base_url = base_url
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeIndex:
    def __init__(self, *, path: Path):
        self.path = path
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_main_passes_paths_prints_json_and_closes_resources(monkeypatch, tmp_path, capsys):
    calls = {}
    corpus = object()
    result = type("Result", (), {"embedded_chunk_count": 3, "skipped_pack_count": 1,
                                  "deleted_pack_ids": ("old-pack",)})()
    def load(path):
        calls["corpus_path"] = path
        return corpus
    def make_embedder(**kwargs):
        calls["embedder"] = FakeEmbedder(**kwargs)
        return calls["embedder"]
    def make_index(**kwargs):
        calls["index"] = FakeIndex(**kwargs)
        return calls["index"]
    monkeypatch.setattr(indexing, "load_ingested_corpus", load)
    monkeypatch.setattr(indexing, "OllamaEmbeddingProvider", make_embedder)
    monkeypatch.setattr(indexing, "QdrantLocalVectorIndex", make_index)

    class FakeIndexer:
        def __init__(self, **kwargs):
            calls["indexer"] = kwargs

        def build(self, received):
            assert received is corpus
            return result
    monkeypatch.setattr(indexing, "RagIndexer", FakeIndexer)

    assert indexing.main(
        ["--generated-root", "generated", "--vector-root", "vectors", "--ollama-base-url", "http://test"]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "status": "ready",
        "embedded_chunk_count": 3,
        "skipped_pack_count": 1,
        "deleted_pack_ids": ["old-pack"],
    }
    assert calls["corpus_path"] == Path("generated")
    assert calls["index"].path == Path("vectors/coc7")
    assert calls["indexer"]["manifest_path"] == Path("vectors/coc7_rules-manifest.json")
    assert calls["embedder"].base_url == "http://test"
    assert calls["embedder"].closed and calls["index"].closed


def test_main_closes_both_resources_and_propagates_build_error(monkeypatch, tmp_path):
    embedder = FakeEmbedder(base_url="x")
    vector_index = FakeIndex(path=tmp_path / "coc7")
    monkeypatch.setattr(indexing, "load_ingested_corpus", lambda _: object())
    monkeypatch.setattr(indexing, "OllamaEmbeddingProvider", lambda **_: embedder)
    monkeypatch.setattr(indexing, "QdrantLocalVectorIndex", lambda **_: vector_index)
    def broken_indexer(**_):
        def build(*_args):
            raise ValueError("boom")

        return type("Broken", (), {"build": build})()

    monkeypatch.setattr(indexing, "RagIndexer", broken_indexer)
    with pytest.raises(ValueError, match="boom"):
        indexing.main(["--generated-root", "generated", "--vector-root", str(tmp_path / "vectors")])
    assert embedder.closed and vector_index.closed


def test_prepare_rules_contract_is_static():
    script = Path(__file__).parents[2].joinpath("scripts/prepare-rules.sh").read_text()
    assert "ollama pull" not in script
    assert "ollama list" in script
    assert "--no-cache" not in script
    assert "ingestion" in script and "indexing" in script
