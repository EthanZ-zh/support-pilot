from functools import lru_cache

from support_pilot.config import get_settings
from support_pilot.rag.providers.base import EmbeddingProvider, RerankerProvider
from support_pilot.rag.providers.deterministic import (
    DeterministicEmbeddingProvider,
    DeterministicRerankerProvider,
)


@lru_cache(maxsize=2)
def get_provider_bundle(kind: str | None = None) -> tuple[EmbeddingProvider, RerankerProvider]:
    settings = get_settings()
    selected = kind or settings.retrieval_provider
    if selected == "deterministic":
        return DeterministicEmbeddingProvider(), DeterministicRerankerProvider()
    if selected == "local_bge":
        from support_pilot.rag.providers.local_bge import (
            LocalBgeEmbeddingProvider,
            LocalBgeRerankerProvider,
        )

        cache_dir = settings.model_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        return (
            LocalBgeEmbeddingProvider(
                model_name=settings.embedding_model,
                cache_dir=cache_dir,
            ),
            LocalBgeRerankerProvider(
                model_name=settings.reranker_model,
                cache_dir=cache_dir,
            ),
        )
    raise ValueError(f"unsupported retrieval provider: {selected}")
