import argparse
from pathlib import Path

from support_pilot.infrastructure.database import get_session_factory
from support_pilot.rag.ingestion import ingest_manifest
from support_pilot.rag.providers.factory import get_provider_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest synthetic ExampleAPI knowledge")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "local_bge"),
        default="deterministic",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/knowledge/manifest.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    embedding, _reranker = get_provider_bundle(args.provider)
    with get_session_factory()() as session:
        document_count, chunk_count = ingest_manifest(
            session,
            manifest_path=args.manifest,
            embedding_provider=embedding,
        )
    print(
        f"Ingested {document_count} synthetic documents and {chunk_count} chunks "
        f"with {embedding.provider_name}/{embedding.model_name}."
    )


if __name__ == "__main__":
    main()
