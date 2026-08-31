from support_pilot.config import get_settings
from support_pilot.rag.providers.factory import get_provider_bundle


def main() -> None:
    settings = get_settings()
    embedding, reranker = get_provider_bundle("local_bge")
    print(f"Embedding ready: {embedding.model_name}")
    print(f"Reranker ready: {reranker.model_name}")
    print(f"Model cache: {settings.model_cache_dir.resolve()}")


if __name__ == "__main__":
    main()
