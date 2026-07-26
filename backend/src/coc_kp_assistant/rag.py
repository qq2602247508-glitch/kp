import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

PRODUCT_NAMESPACE = "local-coc-kp-assistant"
RULESET_NAMESPACE = "coc7e"
COLLECTION_NAME = "coc7_rules"
EMBEDDING_MODEL = "bge-m3:latest"
MANIFEST_SCHEMA_VERSION = 2
CHUNKER_NAME = "coc7-heading-page"
CHUNKER_VERSION = 1
CHUNK_MAX_CHARS = 1200
_CHUNK_NAMESPACE = uuid.UUID("13fd1904-a77d-58a4-940a-bb3f46d34e39")
_DEFAULT_SEARCH_PACK_POLICY = {
    "coc7e.core.zh-v1.2.1": ("core", "core"),
    "coc7e.investigator-handbook.zh-v1.21": ("supplement", "investigator"),
}


@dataclass(frozen=True)
class Corpus:
    product: str
    ruleset: str
    records: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        if self.product != PRODUCT_NAMESPACE or self.ruleset != RULESET_NAMESPACE:
            raise ValueError("COC product and ruleset namespaces are required")
        for record in self.records:
            if record.get("ruleset") != self.ruleset:
                raise ValueError("record ruleset does not match the COC corpus")
            if type(record.get("default_enabled")) is not bool:
                raise ValueError("record default_enabled must be a boolean")


@dataclass(frozen=True)
class ChunkMetadata:
    source_pack: str
    edition: str
    tier: str
    module: str
    era: tuple[str, ...]
    filename: str
    page: int | None
    section: str
    checksum: str
    enabled_by_default: bool
    legacy: bool

    def as_payload(self) -> dict[str, Any]:
        return {
            "checksum": self.checksum,
            "edition": self.edition,
            "enabled_by_default": self.enabled_by_default,
            "era": list(self.era),
            "filename": self.filename,
            "legacy": self.legacy,
            "module": self.module,
            "page": self.page,
            "section": self.section,
            "source_pack": self.source_pack,
            "tier": self.tier,
        }


@dataclass(frozen=True)
class RuleChunk:
    chunk_id: str
    text: str
    metadata: ChunkMetadata


@dataclass(frozen=True)
class VectorPoint:
    chunk: RuleChunk
    vector: list[float]


@dataclass(frozen=True)
class CollectionState:
    exists: bool
    vector_size: int | None
    point_count: int
    corpus_digest: str | None = None


@dataclass(frozen=True)
class SearchHit:
    chunk: RuleChunk
    score: float


@dataclass(frozen=True)
class SearchOptions:
    enabled_pack_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildResult:
    embedded_chunk_count: int
    skipped_pack_count: int
    deleted_pack_ids: tuple[str, ...]


class IndexCompatibilityError(RuntimeError):
    pass


class IndexIncompleteError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorIndex(Protocol):
    collection_name: str

    def state(self) -> CollectionState: ...

    def prepare(self, vector_size: int, *, recreate: bool = False) -> None: ...

    def delete_packs(self, pack_ids: set[str]) -> None: ...

    def upsert(self, points: list[VectorPoint]) -> None: ...

    def set_corpus_digest(self, corpus_digest: str) -> None: ...

    def search(
        self, vector: list[float], *, allowed_pack_ids: set[str], limit: int
    ) -> list[SearchHit]: ...


class OllamaEmbeddingProvider:
    model_name = EMBEDDING_MODEL

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        base_url: str = "http://127.0.0.1:11434",
        dimension: int = 1024,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            raise ValueError("embedding batch size must be positive")
        self.dimension = dimension
        self._client = client or httpx.Client(timeout=120.0)
        self._base_url = base_url.rstrip("/")
        self._batch_size = batch_size
        self._owns_client = client is None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self._batch_size]))
        _validate_vectors(vectors, expected_count=len(texts), dimension=self.dimension)
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.post(
                f"{self._base_url}/api/embed",
                json={
                    "input": texts,
                    "model": self.model_name,
                    "truncate": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            raise IndexIncompleteError("Ollama embedding request failed") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("embeddings"), list):
            raise IndexIncompleteError("Ollama returned an invalid embedding response")
        raw_vectors = cast(list[object], payload["embeddings"])
        vectors: list[list[float]] = []
        for raw_vector in raw_vectors:
            if not isinstance(raw_vector, list) or not all(
                isinstance(value, int | float) for value in raw_vector
            ):
                raise IndexIncompleteError("Ollama returned an invalid embedding vector")
            vectors.append([float(value) for value in raw_vector])
        _validate_vectors(vectors, expected_count=len(texts), dimension=self.dimension)
        return vectors

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class QdrantLocalVectorIndex:
    collection_name = COLLECTION_NAME

    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._client = QdrantClient(path=str(path))

    def state(self) -> CollectionState:
        if not self._client.collection_exists(self.collection_name):
            return CollectionState(False, None, 0)
        details = self._client.get_collection(self.collection_name)
        vector_config = details.config.params.vectors
        if not isinstance(vector_config, qdrant_models.VectorParams):
            raise IndexCompatibilityError("named or sparse Qdrant vectors are not supported")
        collection_metadata = details.config.metadata
        corpus_digest = (
            collection_metadata.get("corpus_digest")
            if isinstance(collection_metadata, dict)
            else None
        )
        return CollectionState(
            exists=True,
            vector_size=vector_config.size,
            point_count=details.points_count or 0,
            corpus_digest=corpus_digest if isinstance(corpus_digest, str) else None,
        )

    def prepare(self, vector_size: int, *, recreate: bool = False) -> None:
        exists = self._client.collection_exists(self.collection_name)
        if recreate and exists:
            self._client.delete_collection(self.collection_name)
            exists = False
        if not exists:
            self._client.create_collection(
                self.collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
            return
        if self.state().vector_size != vector_size:
            raise IndexCompatibilityError("Qdrant collection vector dimension is incompatible")

    def delete_packs(self, pack_ids: set[str]) -> None:
        if not pack_ids:
            return
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=qdrant_models.FilterSelector(
                filter=_pack_filter(pack_ids),
            ),
            wait=True,
        )

    def upsert(self, points: list[VectorPoint]) -> None:
        if not points:
            return
        self._client.upsert(
            collection_name=self.collection_name,
            points=[
                qdrant_models.PointStruct(
                    id=point.chunk.chunk_id,
                    vector=point.vector,
                    payload={
                        "chunk_id": point.chunk.chunk_id,
                        "text": point.chunk.text,
                        **point.chunk.metadata.as_payload(),
                    },
                )
                for point in points
            ],
            wait=True,
        )

    def set_corpus_digest(self, corpus_digest: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", corpus_digest):
            raise ValueError("corpus digest must be a lowercase SHA-256")
        self._client.update_collection(
            collection_name=self.collection_name,
            metadata={"corpus_digest": corpus_digest},
        )

    def search(
        self, vector: list[float], *, allowed_pack_ids: set[str], limit: int
    ) -> list[SearchHit]:
        if not allowed_pack_ids:
            return []
        response = self._client.query_points(
            collection_name=self.collection_name,
            query=vector,
            query_filter=_pack_filter(allowed_pack_ids),
            limit=limit,
            with_payload=True,
        )
        return [
            SearchHit(chunk=_chunk_from_qdrant_payload(point.payload), score=float(point.score))
            for point in response.points
        ]

    def close(self) -> None:
        self._client.close()


def _pack_filter(pack_ids: set[str]) -> qdrant_models.Filter:
    return qdrant_models.Filter(
        must=[
            qdrant_models.FieldCondition(
                key="source_pack",
                match=qdrant_models.MatchAny(any=sorted(pack_ids)),
            )
        ]
    )


def _chunk_from_qdrant_payload(payload: dict[str, Any] | None) -> RuleChunk:
    if not isinstance(payload, dict):
        raise IndexIncompleteError("Qdrant search result is missing its payload")
    era = payload.get("era")
    if not isinstance(era, list) or not all(isinstance(value, str) for value in era):
        raise IndexIncompleteError("Qdrant search result has invalid era provenance")
    page = payload.get("page")
    if page is not None and (not isinstance(page, int) or isinstance(page, bool)):
        raise IndexIncompleteError("Qdrant search result has invalid page provenance")
    enabled_by_default = _required_payload_bool(payload, "enabled_by_default")
    legacy = _required_payload_bool(payload, "legacy")
    return RuleChunk(
        chunk_id=_required_string(payload.get("chunk_id"), "Qdrant chunk id"),
        text=_required_string(payload.get("text"), "Qdrant chunk text"),
        metadata=ChunkMetadata(
            source_pack=_required_string(payload.get("source_pack"), "Qdrant source pack"),
            edition=_required_string(payload.get("edition"), "Qdrant edition"),
            tier=_required_string(payload.get("tier"), "Qdrant tier"),
            module=_required_string(payload.get("module"), "Qdrant module"),
            era=tuple(cast(list[str], era)),
            filename=_required_string(payload.get("filename"), "Qdrant filename"),
            page=page,
            section=_required_string(payload.get("section"), "Qdrant section"),
            checksum=_required_string(payload.get("checksum"), "Qdrant checksum"),
            enabled_by_default=enabled_by_default,
            legacy=legacy,
        ),
    )


def _required_payload_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if type(value) is not bool:
        raise IndexIncompleteError(f"Qdrant {field} metadata must be a boolean")
    return value


class RagIndexer:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        vector_index: VectorIndex,
        manifest_path: Path,
    ) -> None:
        self._embedder = embedder
        self._vector_index = vector_index
        self._manifest_path = manifest_path

    def build(self, corpus: Corpus) -> BuildResult:
        _require_runtime_identity(self._embedder, self._vector_index)
        chunks = chunk_corpus(corpus)
        current_packs = _pack_manifest(corpus, chunks)
        previous = _read_manifest(self._manifest_path)
        recreate = False
        previous_packs: dict[str, dict[str, object]] = {}
        if previous is not None:
            _require_compatible_manifest(previous, self._embedder, self._vector_index)
            if previous.get("status") == "complete":
                _require_collection_matches(
                    previous, self._vector_index.state(), context="existing index"
                )
                previous_packs = _manifest_packs(previous)
            else:
                recreate = True
        elif self._vector_index.state().exists:
            raise IndexCompatibilityError("vector collection exists without an index manifest")

        changed = {
            pack_id
            for pack_id, pack in current_packs.items()
            if previous_packs.get(pack_id) != pack
        }
        removed = set(previous_packs) - set(current_packs)
        deleted = changed | removed
        building_manifest = _make_manifest(
            status="building",
            embedder=self._embedder,
            vector_index=self._vector_index,
            packs=current_packs,
            chunks=chunks,
        )
        _write_manifest(self._manifest_path, building_manifest)
        self._vector_index.prepare(self._embedder.dimension, recreate=recreate)
        if deleted and not recreate:
            self._vector_index.delete_packs(deleted)

        changed_chunks = [
            chunk for chunk in chunks if chunk.metadata.source_pack in changed or recreate
        ]
        if changed_chunks:
            vectors = self._embedder.embed([chunk.text for chunk in changed_chunks])
            _validate_vectors(
                vectors,
                expected_count=len(changed_chunks),
                dimension=self._embedder.dimension,
            )
            self._vector_index.upsert(
                [
                    VectorPoint(chunk=chunk, vector=vector)
                    for chunk, vector in zip(changed_chunks, vectors, strict=True)
                ]
            )

        state = self._vector_index.state()
        if state.point_count != len(chunks):
            raise IndexIncompleteError(
                f"vector point count {state.point_count} does not match {len(chunks)} chunks"
            )
        if state.vector_size != self._embedder.dimension:
            raise IndexIncompleteError("vector dimension does not match the embedding manifest")
        corpus_digest = building_manifest["corpus_digest"]
        assert isinstance(corpus_digest, str)
        self._vector_index.set_corpus_digest(corpus_digest)
        state = self._vector_index.state()
        if state.corpus_digest != corpus_digest:
            raise IndexIncompleteError("vector corpus identity was not persisted")
        complete_manifest = dict(building_manifest)
        complete_manifest["status"] = "complete"
        _write_manifest(self._manifest_path, complete_manifest)
        return BuildResult(
            embedded_chunk_count=len(changed_chunks),
            skipped_pack_count=len(current_packs) - len(changed),
            deleted_pack_ids=tuple(sorted(deleted)),
        )


class RagSearcher:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        vector_index: VectorIndex,
        manifest_path: Path,
    ) -> None:
        self._embedder = embedder
        self._vector_index = vector_index
        self._manifest_path = manifest_path

    def search(
        self, query: str, *, options: SearchOptions | None = None, limit: int = 8
    ) -> list[SearchHit]:
        _require_runtime_identity(self._embedder, self._vector_index)
        if not query.strip():
            raise ValueError("search query must not be empty")
        if limit < 1:
            raise ValueError("search limit must be positive")
        manifest = _read_manifest(self._manifest_path)
        if manifest is None:
            raise IndexIncompleteError("complete index manifest is required")
        _require_compatible_manifest(manifest, self._embedder, self._vector_index)
        if manifest.get("status") != "complete":
            raise IndexIncompleteError("index manifest is not complete")
        _require_collection_matches(manifest, self._vector_index.state(), context="search")
        packs = _manifest_packs(manifest)
        requested = set((options or SearchOptions()).enabled_pack_ids)
        unknown = requested - set(packs)
        if unknown:
            raise IndexCompatibilityError(
                f"requested source pack is not indexed: {', '.join(sorted(unknown))}"
            )
        allowed = {
            pack_id
            for pack_id, pack in packs.items()
            if _is_default_search_pack(pack_id, pack)
        } | requested
        vectors = self._embedder.embed([query.strip()])
        _validate_vectors(vectors, expected_count=1, dimension=self._embedder.dimension)
        hits = self._vector_index.search(vectors[0], allowed_pack_ids=allowed, limit=limit)
        for hit in hits:
            pack_id = hit.chunk.metadata.source_pack
            pack = packs.get(pack_id)
            if pack_id not in allowed or pack is None:
                raise IndexIncompleteError("vector search returned a disallowed source pack")
            if hit.chunk.metadata.checksum != pack.get("checksum"):
                raise IndexIncompleteError("vector search returned stale source provenance")
        return hits


def load_ingested_corpus(
    output_root: Path, *, product: str = PRODUCT_NAMESPACE
) -> Corpus:
    report = _read_ingestion_object(output_root / "ingestion-report.json", "report")
    if report.get("status") != "ready" or report.get("ruleset") != RULESET_NAMESPACE:
        raise ValueError("ingestion report is not a ready COC7 corpus")
    pack_reports = report.get("packs")
    if not isinstance(pack_reports, list):
        raise ValueError("ingestion report packs are invalid")
    expected: dict[str, dict[str, object]] = {}
    for value in pack_reports:
        pack_report = _mapping(value, "ingestion pack report")
        pack_id = _required_string(pack_report.get("pack_id"), "ingestion pack id")
        if pack_report.get("status") != "ready":
            raise ValueError("ingestion report contains an incomplete pack")
        checksum = pack_report.get("sha256")
        if not isinstance(checksum, str):
            raise ValueError("ingestion report pack checksum is invalid")
        expected[pack_id] = pack_report
    records_root = output_root / "records"
    actual_paths = {
        path.stem: path for path in records_root.glob("*.json") if path.is_file()
    }
    if set(actual_paths) != set(expected):
        raise ValueError("ingestion records do not match the ready pack report")
    records: list[dict[str, object]] = []
    for pack_id in sorted(expected):
        record = _read_ingestion_object(actual_paths[pack_id], "record")
        provenance = _mapping(record.get("provenance"), "ingestion record provenance")
        if (
            record.get("pack_id") != pack_id
            or record.get("ruleset") != RULESET_NAMESPACE
            or provenance.get("sha256") != expected[pack_id].get("sha256")
            or record.get("default_enabled")
            != expected[pack_id].get("default_enabled")
        ):
            raise ValueError("ingestion record does not match its ready pack report")
        records.append(record)
    return Corpus(product, RULESET_NAMESPACE, tuple(records))


def _read_ingestion_object(path: Path, kind: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"ingestion {kind} is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError(f"ingestion {kind} must be an object")
    return cast(dict[str, object], value)


def _require_runtime_identity(
    embedder: EmbeddingProvider, vector_index: VectorIndex
) -> None:
    if embedder.model_name != EMBEDDING_MODEL:
        raise IndexCompatibilityError(
            f"embedding model must be the installed {EMBEDDING_MODEL}"
        )
    if embedder.dimension < 1:
        raise IndexCompatibilityError("embedding dimension must be positive")
    if vector_index.collection_name != COLLECTION_NAME:
        raise IndexCompatibilityError(
            f"vector collection must use isolated namespace {COLLECTION_NAME}"
        )


def _pack_manifest(
    corpus: Corpus, chunks: tuple[RuleChunk, ...]
) -> dict[str, dict[str, object]]:
    chunks_by_pack: dict[str, list[RuleChunk]] = {}
    for chunk in chunks:
        chunks_by_pack.setdefault(chunk.metadata.source_pack, []).append(chunk)
    packs: dict[str, dict[str, object]] = {}
    for record in corpus.records:
        pack_id = _required_string(record.get("pack_id"), "pack_id")
        if pack_id in packs:
            raise ValueError(f"duplicate source pack: {pack_id}")
        provenance = _mapping(record.get("provenance"), "record provenance")
        pack_chunks = chunks_by_pack.get(pack_id, [])
        descriptor: dict[str, object] = {
            "checksum": _required_string(provenance.get("sha256"), "provenance sha256"),
            "chunk_count": len(pack_chunks),
            "edition": _required_string(record.get("edition"), "edition"),
            "enabled_by_default": record["default_enabled"],
            "era": list(pack_chunks[0].metadata.era) if pack_chunks else [],
            "filename": _required_string(provenance.get("filename"), "provenance filename"),
            "legacy": record.get("kind") == "legacy",
            "module": _required_string(record.get("kind"), "kind"),
            "tier": _tier_for_module(_required_string(record.get("kind"), "kind")),
        }
        descriptor["chunk_digest"] = hashlib.sha256(
            "\n".join(chunk.chunk_id for chunk in pack_chunks).encode("utf-8")
        ).hexdigest()
        packs[pack_id] = descriptor
    return dict(sorted(packs.items()))


def _make_manifest(
    *,
    status: str,
    embedder: EmbeddingProvider,
    vector_index: VectorIndex,
    packs: dict[str, dict[str, object]],
    chunks: tuple[RuleChunk, ...],
) -> dict[str, object]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "product": PRODUCT_NAMESPACE,
        "ruleset": RULESET_NAMESPACE,
        "collection": vector_index.collection_name,
        "status": status,
        "chunker": _chunker_manifest(),
        "embedding": {
            "model": embedder.model_name,
            "dimension": embedder.dimension,
        },
        "chunk_count": len(chunks),
        "corpus_digest": _corpus_digest(packs),
        "packs": packs,
    }


def _read_manifest(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IndexCompatibilityError("index manifest is unreadable") from error
    if not isinstance(value, dict):
        raise IndexCompatibilityError("index manifest must be an object")
    return cast(dict[str, object], value)


def _write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _require_compatible_manifest(
    manifest: dict[str, object],
    embedder: EmbeddingProvider,
    vector_index: VectorIndex,
) -> None:
    expected: tuple[tuple[str, object], ...] = (
        ("schema_version", MANIFEST_SCHEMA_VERSION),
        ("product", PRODUCT_NAMESPACE),
        ("ruleset", RULESET_NAMESPACE),
        ("collection", vector_index.collection_name),
    )
    for field, value in expected:
        if manifest.get(field) != value:
            raise IndexCompatibilityError(f"index manifest {field} is incompatible")
    if manifest.get("chunker") != _chunker_manifest():
        raise IndexCompatibilityError("index manifest chunker is incompatible")
    embedding = manifest.get("embedding")
    if not isinstance(embedding, dict):
        raise IndexCompatibilityError("index manifest embedding is invalid")
    if embedding.get("model") != embedder.model_name:
        raise IndexCompatibilityError("index manifest embedding model is incompatible")
    if embedding.get("dimension") != embedder.dimension:
        raise IndexCompatibilityError("index manifest embedding dimension is incompatible")
    if not isinstance(manifest.get("chunk_count"), int):
        raise IndexCompatibilityError("index manifest chunk count is invalid")
    packs = _manifest_packs(manifest)
    corpus_digest = manifest.get("corpus_digest")
    if (
        not isinstance(corpus_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", corpus_digest)
        or corpus_digest != _corpus_digest(packs)
    ):
        raise IndexCompatibilityError("index manifest corpus digest is incompatible")


def _manifest_packs(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    value = manifest.get("packs")
    if not isinstance(value, dict):
        raise IndexCompatibilityError("index manifest packs are invalid")
    result: dict[str, dict[str, object]] = {}
    for pack_id, descriptor in value.items():
        if not isinstance(pack_id, str) or not isinstance(descriptor, dict):
            raise IndexCompatibilityError("index manifest pack entry is invalid")
        required = {
            "checksum",
            "chunk_count",
            "chunk_digest",
            "edition",
            "enabled_by_default",
            "era",
            "filename",
            "legacy",
            "module",
            "tier",
        }
        if not required.issubset(descriptor):
            missing = required - set(descriptor)
            if "chunk_digest" in missing:
                raise IndexCompatibilityError("index manifest pack chunk digest is missing")
            raise IndexCompatibilityError("index manifest pack entry is incomplete")
        typed_descriptor = cast(dict[str, object], descriptor)
        _validate_pack_descriptor(typed_descriptor)
        result[pack_id] = typed_descriptor
    return result


def _validate_pack_descriptor(descriptor: dict[str, object]) -> None:
    for field in ("checksum", "chunk_digest"):
        value = descriptor[field]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            readable_field = field.replace("_", " ")
            raise IndexCompatibilityError(
                f"index manifest pack {readable_field} is invalid"
            )
    chunk_count = descriptor["chunk_count"]
    if (
        not isinstance(chunk_count, int)
        or isinstance(chunk_count, bool)
        or chunk_count < 0
    ):
        raise IndexCompatibilityError("index manifest pack chunk count is invalid")
    for field in ("edition", "filename", "module", "tier"):
        if not isinstance(descriptor[field], str) or not descriptor[field]:
            raise IndexCompatibilityError(f"index manifest pack {field} is invalid")
    era = descriptor["era"]
    if not isinstance(era, list) or not all(isinstance(value, str) for value in era):
        raise IndexCompatibilityError("index manifest pack era is invalid")
    for field in ("enabled_by_default", "legacy"):
        if type(descriptor[field]) is not bool:
            raise IndexCompatibilityError(f"index manifest pack {field} is invalid")


def _chunker_manifest() -> dict[str, object]:
    return {
        "name": CHUNKER_NAME,
        "version": CHUNKER_VERSION,
        "config": {"max_chars": CHUNK_MAX_CHARS},
    }


def _corpus_digest(packs: dict[str, dict[str, object]]) -> str:
    canonical = json.dumps(
        packs,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_default_search_pack(pack_id: str, pack: dict[str, object]) -> bool:
    expected = _DEFAULT_SEARCH_PACK_POLICY.get(pack_id)
    return (
        expected is not None
        and pack["enabled_by_default"] is True
        and pack["legacy"] is False
        and (pack["tier"], pack["module"]) == expected
    )


def _require_collection_matches(
    manifest: dict[str, object], state: CollectionState, *, context: str
) -> None:
    if not state.exists:
        raise IndexIncompleteError(f"{context} vector collection is missing")
    embedding = cast(dict[str, object], manifest["embedding"])
    if state.vector_size != embedding["dimension"]:
        raise IndexIncompleteError(f"{context} vector dimension does not match")
    if state.point_count != manifest["chunk_count"]:
        raise IndexIncompleteError(f"{context} vector point count does not match")
    if state.corpus_digest != manifest["corpus_digest"]:
        raise IndexCompatibilityError(f"{context} vector corpus identity does not match")


def _validate_vectors(
    vectors: list[list[float]], *, expected_count: int, dimension: int
) -> None:
    if len(vectors) != expected_count:
        raise IndexIncompleteError("embedding provider returned the wrong vector count")
    if any(len(vector) != dimension for vector in vectors):
        raise IndexIncompleteError("embedding provider returned the wrong vector dimension")


def chunk_corpus(
    corpus: Corpus, *, max_chars: int = CHUNK_MAX_CHARS
) -> tuple[RuleChunk, ...]:
    if max_chars < 40:
        raise ValueError("max_chars must be at least 40")
    chunks: list[RuleChunk] = []
    for record in sorted(corpus.records, key=lambda item: str(item.get("pack_id", ""))):
        chunks.extend(_chunk_record(record, max_chars=max_chars))
    return tuple(chunks)


@dataclass(frozen=True)
class _SourceUnit:
    locator: str
    page: int | None
    text: str


def _chunk_record(record: dict[str, object], *, max_chars: int) -> list[RuleChunk]:
    provenance = _mapping(record.get("provenance"), "record provenance")
    pack_id = _required_string(record.get("pack_id"), "pack_id")
    edition = _required_string(record.get("edition"), "edition")
    module = _required_string(record.get("kind"), "kind")
    filename = _required_string(provenance.get("filename"), "provenance filename")
    checksum = _required_string(provenance.get("sha256"), "provenance sha256")
    eras_value = provenance.get("eras", [])
    if not isinstance(eras_value, list) or not all(isinstance(item, str) for item in eras_value):
        raise ValueError("provenance eras must be a list of strings")
    eras = tuple(cast(list[str], eras_value))
    tier = _tier_for_module(module)
    enabled_by_default = cast(bool, record["default_enabled"])
    identity_metadata = json.dumps(
        {
            "edition": edition,
            "enabled_by_default": enabled_by_default,
            "era": list(eras),
            "filename": filename,
            "legacy": module == "legacy",
            "module": module,
            "tier": tier,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result: list[RuleChunk] = []
    for unit in _source_units(record):
        for section, section_text in _heading_sections(unit.text, fallback=unit.locator):
            for ordinal, text in enumerate(
                _bounded_text(section_text, max_chars=max_chars), start=1
            ):
                identity = "\x1f".join(
                    (
                        pack_id,
                        unit.locator,
                        section,
                        str(ordinal),
                        identity_metadata,
                        hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    )
                )
                result.append(
                    RuleChunk(
                        chunk_id=str(uuid.uuid5(_CHUNK_NAMESPACE, identity)),
                        text=text,
                        metadata=ChunkMetadata(
                            source_pack=pack_id,
                            edition=edition,
                            tier=tier,
                            module=module,
                            era=eras,
                            filename=filename,
                            page=unit.page,
                            section=section,
                            checksum=checksum,
                            enabled_by_default=enabled_by_default,
                            legacy=module == "legacy",
                        ),
                    )
                )
    return result


def _source_units(record: dict[str, object]) -> list[_SourceUnit]:
    content = _mapping(record.get("content"), "record content")
    units: list[_SourceUnit] = []
    pages = content.get("pages")
    if isinstance(pages, list):
        for page_value in pages:
            page = _mapping(page_value, "page")
            page_number = page.get("page_number")
            if not isinstance(page_number, int):
                raise ValueError("page number must be an integer")
            units.append(
                _SourceUnit(
                    locator=_unit_locator(page, f"page:{page_number}"),
                    page=page_number,
                    text=_required_string(page.get("text"), "page text", allow_empty=True),
                )
            )
    paragraphs = content.get("paragraphs")
    if isinstance(paragraphs, list):
        for index, paragraph_value in enumerate(paragraphs, start=1):
            paragraph = _mapping(paragraph_value, "paragraph")
            units.append(
                _SourceUnit(
                    locator=_unit_locator(paragraph, f"paragraph:{index}"),
                    page=None,
                    text=_required_string(
                        paragraph.get("text"), "paragraph text", allow_empty=True
                    ),
                )
            )
    tables = content.get("tables")
    if isinstance(tables, list):
        for index, table_value in enumerate(tables, start=1):
            table = _mapping(table_value, "table")
            rows = table.get("rows")
            if not isinstance(rows, list):
                raise ValueError("table rows must be a list")
            row_text: list[str] = []
            for row in rows:
                if not isinstance(row, list):
                    raise ValueError("table row must be a list")
                row_text.append("\t".join("" if value is None else str(value) for value in row))
            units.append(
                _SourceUnit(
                    locator=_unit_locator(table, f"table:{index}"),
                    page=None,
                    text="\n".join(row_text),
                )
            )
    sheets = content.get("sheets")
    if isinstance(sheets, list):
        for sheet_value in sheets:
            sheet = _mapping(sheet_value, "sheet")
            name = _required_string(sheet.get("name"), "sheet name")
            cells = sheet.get("cells")
            if not isinstance(cells, list):
                raise ValueError("sheet cells must be a list")
            cell_text: list[str] = []
            for cell_value in cells:
                cell = _mapping(cell_value, "cell")
                coordinate = _required_string(cell.get("coordinate"), "cell coordinate")
                value = cell.get("value")
                if value not in (None, ""):
                    cell_text.append(f"{coordinate}: {value}")
            units.append(
                _SourceUnit(
                    locator=_unit_locator(sheet, f"sheet:{name}"),
                    page=None,
                    text="\n".join(cell_text),
                )
            )
    return [unit for unit in units if unit.text.strip()]


def _heading_sections(text: str, *, fallback: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_name = fallback
    current_lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw_line.strip()
        heading = _heading_name(line)
        if heading is not None:
            if current_lines:
                sections.append((current_name, current_lines))
            current_name = heading
            current_lines = [heading]
        elif line:
            current_lines.append(line)
        elif current_lines and current_lines[-1] != "":
            current_lines.append("")
    if current_lines:
        sections.append((current_name, current_lines))
    return [
        (name, "\n".join(lines).strip())
        for name, lines in sections
        if "\n".join(lines).strip()
    ]


def _heading_name(line: str) -> str | None:
    markdown = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
    if markdown:
        return markdown.group(1)
    numbered = re.match(r"^(?:第.{1,20}[章节篇]|(?:\d+\.)+\d*)\s*(.{1,80})$", line)
    if numbered:
        return line
    if 1 < len(line) <= 80 and line.endswith((":", "：")):
        return line[:-1].strip()
    return None


def _bounded_text(text: str, *, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for part in _hard_split(paragraph, max_chars=max_chars):
            candidate = f"{current}\n\n{part}" if current else part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = part
    if current:
        chunks.append(current)
    return chunks


def _hard_split(text: str, *, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    result: list[str] = []
    remainder = text
    while len(remainder) > max_chars:
        split_at = max(
            remainder.rfind("\n", 0, max_chars + 1),
            remainder.rfind(" ", 0, max_chars + 1),
        )
        if split_at < max_chars // 2:
            split_at = max_chars
        result.append(remainder[:split_at].strip())
        remainder = remainder[split_at:].strip()
    if remainder:
        result.append(remainder)
    return result


def _tier_for_module(module: str) -> str:
    if module == "core":
        return "core"
    if module in {"investigator", "quickstart"}:
        return "supplement"
    if module == "legacy":
        return "legacy"
    return "optional"


def _unit_locator(unit: dict[str, object], fallback: str) -> str:
    provenance = _mapping(unit.get("provenance"), "unit provenance")
    locator = provenance.get("locator")
    return locator if isinstance(locator, str) and locator else fallback


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _required_string(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{name} must be a string")
    return value
