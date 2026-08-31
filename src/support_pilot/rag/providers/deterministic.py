import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from hashlib import sha256

TOKEN_PATTERN = re.compile(r"[a-z0-9_./:-]+|[\u4e00-\u9fff]", re.IGNORECASE)
TECHNICAL_FEATURE_PATTERN = re.compile(r"^[a-z0-9_./:-]+$", re.IGNORECASE)


def lexical_features(text: str) -> list[str]:
    normalized = text.lower()
    tokens = TOKEN_PATTERN.findall(normalized)
    chinese = "".join(token for token in tokens if "\u4e00" <= token <= "\u9fff")
    bigrams = [chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0))]
    return tokens + bigrams


class DeterministicEmbeddingProvider:
    provider_name = "deterministic"
    model_name = "hash-lexical-v1"
    dimensions = 512

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, count in Counter(lexical_features(text)).items():
            digest = sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * float(count)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class DeterministicRerankerProvider:
    provider_name = "deterministic"
    model_name = "weighted-token-overlap-v2"
    answerability_threshold = 0.28

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        query_features = set(lexical_features(query))
        return [self._overlap(query_features, lexical_features(document)) for document in documents]

    @staticmethod
    def _overlap(query_features: set[str], document_features: Iterable[str]) -> float:
        if not query_features:
            return 0.0
        document_set = set(document_features)
        denominator = sum(_feature_weight(feature) for feature in query_features)
        matched = sum(
            _feature_weight(feature) for feature in query_features if feature in document_set
        )
        return matched / denominator if denominator else 0.0


def _feature_weight(feature: str) -> float:
    if TECHNICAL_FEATURE_PATTERN.fullmatch(feature):
        return 3.0
    if len(feature) == 2:
        return 1.5
    return 0.25
