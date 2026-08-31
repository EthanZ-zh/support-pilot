import os
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from typing import Any


class LocalBgeEmbeddingProvider:
    provider_name = "local_bge"
    dimensions = 512

    def __init__(self, *, model_name: str, cache_dir: Path) -> None:
        _configure_huggingface_cache(cache_dir)
        try:
            sentence_transformers = import_module("sentence_transformers")
        except ImportError as error:
            raise RuntimeError(
                "local RAG dependencies are missing; run `uv sync --group rag-local`"
            ) from error
        self.model_name = model_name
        self._model: Any = sentence_transformers.SentenceTransformer(
            model_name,
            cache_folder=str(cache_dir),
            device="cpu",
        )
        actual_dimensions = self._model.get_embedding_dimension()
        if actual_dimensions != self.dimensions:
            raise RuntimeError(
                "embedding model returned "
                f"{actual_dimensions} dimensions; expected {self.dimensions}"
            )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        values = self._model.encode(
            list(texts),
            batch_size=16,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in values]


class LocalBgeRerankerProvider:
    provider_name = "local_bge"
    answerability_threshold = 0.35

    def __init__(self, *, model_name: str, cache_dir: Path) -> None:
        _configure_huggingface_cache(cache_dir)
        try:
            sentence_transformers = import_module("sentence_transformers")
        except ImportError as error:
            raise RuntimeError(
                "local RAG dependencies are missing; run `uv sync --group rag-local`"
            ) from error
        self.model_name = model_name
        self._model: Any = sentence_transformers.CrossEncoder(
            model_name,
            max_length=512,
            device="cpu",
            model_kwargs={"cache_dir": str(cache_dir)},
            processor_kwargs={"cache_dir": str(cache_dir)},
        )

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        raw_scores = self._model.predict(
            [(query, document) for document in documents],
            batch_size=8,
            show_progress_bar=False,
        )
        return [float(score) for score in raw_scores]


def _configure_huggingface_cache(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(cache_dir))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
