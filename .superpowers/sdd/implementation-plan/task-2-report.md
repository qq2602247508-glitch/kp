# Task 2 report: COC-only local RAG index

## Status

Implemented Task 2 only. The implementation adds deterministic chunking,
provider-neutral embedding/vector interfaces, an Ollama `bge-m3:latest`
adapter, embedded local Qdrant storage in the fixed `coc7_rules` collection,
atomic compatibility manifests, pack-level incremental rebuilds, fail-closed
search, and explicit optional/legacy pack enablement.

Commit: `d5283d475ea0a5e635a6accbd783c982c87899f9`

No Task 3 answer generation, API, or UI work was added. No real source book,
existing vector database, or unrelated project path was opened or written.

## Implementation

- `Corpus` enforces product `local-coc-kp-assistant`, ruleset `coc7e`, and
  per-record ruleset compatibility.
- `load_ingested_corpus()` consumes the Task 1
  `ingestion-report.json`/`records/*.json` contract and rejects failed,
  missing, extra, or checksum-mismatched outputs.
- `chunk_corpus()` sorts packs deterministically, never crosses source units
  or PDF pages, recognizes Markdown/numbered/colon headings, and emits UUIDv5
  IDs derived from pack, locator, section, ordinal, and text digest.
- Every Qdrant payload stores source pack, edition, tier, module, era,
  filename, page/section, checksum, enabled-by-default, and legacy metadata.
- `OllamaEmbeddingProvider` calls only `POST /api/embed` with installed model
  `bge-m3:latest`; it never calls a pull endpoint. It validates counts and
  dimensions and batches inputs in groups of 32.
- `QdrantLocalVectorIndex` uses an explicitly supplied local path and the
  fixed `coc7_rules` collection. It creates cosine vectors, upserts complete
  payloads, filters allowed packs in Qdrant, and deletes stale packs by
  payload filter.
- `RagIndexer` writes a `building` manifest before mutation and changes it to
  `complete` only after point-count and dimension verification. Unchanged
  packs are not re-embedded; changed/removed packs are deleted and changed
  packs are rebuilt.
- `RagSearcher` verifies product, ruleset, schema, collection, embedding
  model/dimension, manifest completion, collection count, and hit checksums
  before returning results. Defaults include only enabled, non-legacy packs;
  optional and legacy packs require exact explicit pack IDs.

## Files

- `backend/src/coc_kp_assistant/rag.py`
- `backend/tests/test_rag_chunking.py`
- `backend/tests/test_rag_index.py`
- `backend/tests/test_rag_adapters.py`
- `backend/tests/test_rag_corpus.py`
- `backend/pyproject.toml`
- `backend/uv.lock`

Dependencies added: `httpx>=0.27,<1` and `qdrant-client>=1.12,<2`. `uv.lock`
resolved `qdrant-client==1.18.0`. Qdrant Python dependencies were installed;
no AI model was downloaded or pulled.

## Exact TDD evidence

### Cycle 1: deterministic chunks and COC namespace

Initial collection RED:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_chunking.py
ERROR backend/tests/test_rag_chunking.py
ModuleNotFoundError: No module named 'coc_kp_assistant.rag'
```

After adding only the public skeleton, behavioral RED:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_chunking.py
FFFFF
5 failed
```

GREEN:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_chunking.py
.....                                                                    [100%]
```

### Cycle 2: manifest, incremental rebuild, fail-closed search, filtering

RED:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_index.py
FFFFFF                                                                   [100%]
6 failed
```

GREEN:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_index.py
......                                                                   [100%]
```

### Cycle 3: Ollama and real embedded-Qdrant adapters

RED:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_adapters.py
FF                                                                       [100%]
2 failed
```

GREEN:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_adapters.py
..                                                                       [100%]
```

The Qdrant GREEN test used `QdrantClient(path=<pytest tmp_path>)`, not a fake
Qdrant implementation.

### Cycle 4: Task 1 corpus compatibility

RED:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_corpus.py
FFFF.                                                                    [100%]
4 failed, 1 passed
```

GREEN:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_corpus.py
.....                                                                    [100%]
```

### Cycle 5: production-sized Ollama batching

RED:

```text
$ backend/.venv/bin/pytest -q \
  backend/tests/test_rag_adapters.py::test_ollama_adapter_batches_large_corpora_without_changing_order
F                                                                        [100%]
TypeError: OllamaEmbeddingProvider.__init__() got an unexpected keyword argument 'batch_size'
```

GREEN:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_adapters.py
...                                                                      [100%]
```

Focused aggregate after the first four cycles:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_chunking.py \
  backend/tests/test_rag_index.py backend/tests/test_rag_adapters.py \
  backend/tests/test_rag_corpus.py
..................                                                       [100%]
```

## Final verification

Fresh full backend/domain command:

```text
$ ./scripts/check-domain-isolation.sh
Domain isolation check passed.
$ backend/.venv/bin/ruff check backend
All checks passed!
$ backend/.venv/bin/mypy backend/src
Success: no issues found in 19 source files
$ backend/.venv/bin/pytest -q backend/tests
...........................................................              [100%]
```

Result: 59 backend tests passed.

## Self-review

- Confirmed all writes are limited to this repository, pytest temporary
  directories, the project venv, and uv dependency state.
- Confirmed the production namespace is fixed to `local-coc-kp-assistant`,
  `coc7e`, and `coc7_rules`.
- Confirmed the Qdrant adapter has no default path and therefore cannot
  silently select another project's vector store.
- Confirmed manifests remain `building` after embedding/upsert/count failures,
  so search refuses partial state.
- Confirmed changed or removed packs are deleted before replacement and
  unchanged pack checksums/chunk digests skip embedding.
- Confirmed Qdrant filtering happens at the provider boundary and returned hits
  are revalidated against the manifest.
- Confirmed no model pull/download code, answer generation, completion model,
  API route, or frontend change was introduced.
- `git diff --check` passed.

## Concerns

- Tests intentionally use small synthetic Task 1 records. The installed
  `bge-m3:latest` service and full copyrighted corpus were not exercised in
  this task run; the Ollama HTTP contract is covered with `MockTransport`, and
  Qdrant behavior is covered with a real isolated embedded store.
- Incrementality is pack-level: one changed source checksum rebuilds that pack
  but leaves every unchanged pack untouched. This favors provenance
  consistency because every chunk from a changed source must carry the new
  whole-file checksum.

## Review round 1

### Findings fixed

1. Manifest schema is now version 2 and requires the exact chunker name,
   version, and configuration. Pack descriptors require a valid
   `chunk_digest`; the canonical `corpus_digest` is recomputed and validated.
   The same digest is persisted in Qdrant collection metadata, so search
   rejects a same-namespace manifest belonging to a different collection
   corpus even when collection name, vector size, point count, model, and
   source checksum match.
2. Filename and all non-checksum indexed pack metadata now participate in
   chunk identity. Filename/tier are also in pack descriptors, so a rename
   deletes the stale pack, re-embeds it, changes chunk IDs, and replaces the
   Qdrant payload.
3. Default search now uses an exact approved policy: COC7 core v1.2.1 as
   `core/core` and investigator handbook v1.21 as
   `supplement/investigator`. Optional, quickstart, and legacy packs remain
   opt-in even if malformed input marks them enabled by default.
4. Manifest booleans and Qdrant `enabled_by_default`/`legacy` payload fields
   are required to be real booleans. Missing or non-boolean filter metadata
   fails closed.

### Review TDD evidence

Initial review RED covering all four findings:

```text
$ backend/.venv/bin/pytest -q \
  backend/tests/test_rag_index.py backend/tests/test_rag_adapters.py
.F..FFF..F....FFFF                                                       [100%]
9 failed
```

Those failures reproduced:

- unchanged build and stale payload after a filename rename;
- ignored wrong chunker, wrong corpus digest, and missing pack chunk digest;
- optional/quickstart packs leaking into defaults;
- missing/string/integer Qdrant filter booleans being silently coerced.

GREEN after compatibility, identity, filtering, and strict-payload changes:

```text
$ backend/.venv/bin/pytest -q \
  backend/tests/test_rag_index.py backend/tests/test_rag_adapters.py
..................                                                       [100%]
```

Separate RED for same-namespace, different-corpus manifest replacement:

```text
$ backend/.venv/bin/pytest -q \
  backend/tests/test_rag_index.py::test_search_rejects_a_same_namespace_manifest_for_a_different_corpus
F                                                                        [100%]
Failed: DID NOT RAISE IndexCompatibilityError
```

Separate RED for the real Qdrant collection identity boundary:

```text
$ backend/.venv/bin/pytest -q \
  backend/tests/test_rag_adapters.py::test_qdrant_local_adapter_persists_points_filters_packs_and_deletes_by_pack
F                                                                        [100%]
AttributeError: 'QdrantLocalVectorIndex' object has no attribute 'set_corpus_digest'
```

GREEN for the complete review set:

```text
$ backend/.venv/bin/pytest -q \
  backend/tests/test_rag_index.py backend/tests/test_rag_adapters.py
...................                                                      [100%]
```

Focused aggregate:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_chunking.py \
  backend/tests/test_rag_index.py backend/tests/test_rag_adapters.py \
  backend/tests/test_rag_corpus.py
.............................                                            [100%]
$ backend/.venv/bin/ruff check backend/src/coc_kp_assistant/rag.py \
  backend/tests/test_rag_*.py
All checks passed!
$ backend/.venv/bin/mypy backend/src/coc_kp_assistant/rag.py
Success: no issues found in 1 source file
```

Fresh full backend/domain gate:

```text
$ ./scripts/check-domain-isolation.sh
Domain isolation check passed.
$ backend/.venv/bin/ruff check backend
All checks passed!
$ backend/.venv/bin/mypy backend/src
Success: no issues found in 19 source files
$ backend/.venv/bin/pytest -q backend/tests
.....................................................................    [100%]
```

Result: 69 backend tests passed.

### Review self-review

- Manifest compatibility now validates schema, product, ruleset, collection,
  chunker identity/config, model/dimension, strict pack descriptors, canonical
  corpus digest, collection point count, and the Qdrant-persisted corpus
  digest.
- Collection identity is written only after vectors/count/dimension succeed;
  any earlier failure leaves the manifest in `building`.
- Whole-source checksum remains outside chunk UUID identity, preserving stable
  IDs for unchanged pages, while filename and search-relevant metadata are in
  identity and trigger replacement.
- Default policy cannot be weakened by `default_enabled=true` on an optional
  module.
- No answer-generation, completion-model, route, or UI work was added.

## Takeover verification (2026-07-26)

The interrupted review-fix worktree was inspected before commit. The only
uncommitted files were the Task 2 RAG implementation and its two focused test
modules; the changes match the four documented review findings and introduce
no Task 3, UI, or unrelated-project edits. `git diff --check` passed.

Fresh verification from the takeover:

```text
$ backend/.venv/bin/pytest -q backend/tests/test_rag_chunking.py \
  backend/tests/test_rag_index.py backend/tests/test_rag_adapters.py \
  backend/tests/test_rag_corpus.py
.............................                                            [100%]

$ ./scripts/check-domain-isolation.sh
Domain isolation check passed.
$ backend/.venv/bin/ruff check backend
All checks passed!
$ backend/.venv/bin/mypy backend/src
Success: no issues found in 19 source files
$ backend/.venv/bin/pytest -q backend/tests
.....................................................................    [100%]
```

Result: 29 focused RAG tests and all 69 backend tests passed. No additional
code change was warranted during takeover verification.
