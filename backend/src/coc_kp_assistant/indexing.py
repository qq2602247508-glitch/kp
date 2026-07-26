import argparse
import json
from pathlib import Path

from .rag import (
    OllamaEmbeddingProvider,
    QdrantLocalVectorIndex,
    RagIndexer,
    load_ingested_corpus,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Incrementally build the isolated local COC7 rule index."
    )
    parser.add_argument(
        "--generated-root",
        type=Path,
        required=True,
        help="ready deterministic ingestion output",
    )
    parser.add_argument(
        "--vector-root",
        type=Path,
        required=True,
        help="dedicated COC7 vector root",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="http://127.0.0.1:11434",
        help="loopback Ollama URL; models are never downloaded",
    )
    arguments = parser.parse_args(argv)

    corpus = load_ingested_corpus(arguments.generated_root)
    arguments.vector_root.mkdir(parents=True, exist_ok=True)
    embedder = OllamaEmbeddingProvider(base_url=arguments.ollama_base_url)
    vector_index = QdrantLocalVectorIndex(path=arguments.vector_root / "coc7")
    try:
        result = RagIndexer(
            embedder=embedder,
            vector_index=vector_index,
            manifest_path=arguments.vector_root / "coc7_rules-manifest.json",
        ).build(corpus)
    finally:
        embedder.close()
        vector_index.close()

    print(
        json.dumps(
            {
                "status": "ready",
                "embedded_chunk_count": result.embedded_chunk_count,
                "skipped_pack_count": result.skipped_pack_count,
                "deleted_pack_ids": list(result.deleted_pack_ids),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
