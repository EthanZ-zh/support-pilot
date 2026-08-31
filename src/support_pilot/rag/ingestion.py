import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from support_pilot.infrastructure.models import (
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeDocument,
)
from support_pilot.rag.providers.base import EmbeddingProvider
from support_pilot.rag.providers.deterministic import lexical_features

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class ManifestDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    source_uri: str
    title: str
    doc_type: str
    product_version: str | None = None
    applicable_plans: list[str] = Field(default_factory=list)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    authority: str = "official"
    data_origin: str = "synthetic"
    license: str | None = None
    status: str = "published"
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    content: str
    heading_path: list[str]


class MarkdownChunker:
    def __init__(self, *, max_chars: int = 1_200) -> None:
        self.max_chars = max_chars

    def chunk(self, content: str) -> list[ChunkDraft]:
        heading_stack: list[str] = []
        sections: list[tuple[list[str], list[str]]] = []
        current_lines: list[str] = []
        current_headings: list[str] = []
        for line in content.splitlines():
            heading_match = HEADING_PATTERN.match(line)
            if heading_match is not None:
                if any(part.strip() for part in current_lines):
                    sections.append((current_headings, current_lines))
                level = len(heading_match.group(1))
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(heading_match.group(2).strip())
                current_headings = list(heading_stack)
                current_lines = []
            else:
                current_lines.append(line)
        if any(part.strip() for part in current_lines):
            sections.append((current_headings, current_lines))

        drafts: list[ChunkDraft] = []
        for headings, lines in sections:
            section_text = "\n".join(lines).strip()
            for part in self._split_section(section_text):
                drafts.append(
                    ChunkDraft(
                        ordinal=len(drafts),
                        content=part,
                        heading_path=headings,
                    )
                )
        return drafts

    def _split_section(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text] if text else []
        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
        parts: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 2 > self.max_chars:
                parts.append(current)
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current:
            parts.append(current)
        return parts


def load_manifest(path: Path) -> list[ManifestDocument]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[ManifestDocument]).validate_python(raw)


def ingest_manifest(
    session: Session,
    *,
    manifest_path: Path,
    embedding_provider: EmbeddingProvider,
) -> tuple[int, int]:
    specifications = load_manifest(manifest_path)
    chunker = MarkdownChunker()
    pending_embeddings: list[tuple[KnowledgeChunk, str]] = []
    for specification in specifications:
        file_path = (manifest_path.parent / specification.path).resolve()
        content = file_path.read_text(encoding="utf-8")
        checksum = sha256(content.encode("utf-8")).hexdigest()
        document = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_uri == specification.source_uri
            )
        )
        content_changed = document is not None and document.checksum != checksum
        if document is None:
            document = KnowledgeDocument(
                id=uuid5(NAMESPACE_URL, specification.source_uri),
                source_uri=specification.source_uri,
            )
            session.add(document)
        elif content_changed:
            document.chunks.clear()
            session.flush()
        document.title = specification.title
        document.doc_type = specification.doc_type
        document.product_version = specification.product_version
        document.applicable_plans = specification.applicable_plans
        document.effective_from = specification.effective_from
        document.effective_to = specification.effective_to
        document.authority = specification.authority
        document.data_origin = specification.data_origin
        document.license = specification.license
        document.checksum = checksum
        document.status = specification.status
        existing_chunks = {chunk.id: chunk for chunk in document.chunks}
        for draft in chunker.chunk(content):
            metadata = {
                **specification.metadata,
                "data_origin": specification.data_origin,
                "chunk_key": f"{specification.source_uri}#{draft.ordinal}",
            }
            chunk_id = uuid5(NAMESPACE_URL, f"{specification.source_uri}#{draft.ordinal}")
            chunk = existing_chunks.get(chunk_id)
            if chunk is None:
                chunk = KnowledgeChunk(
                    id=chunk_id,
                    document=document,
                )
                session.add(chunk)
            chunk.ordinal = draft.ordinal
            chunk.content = draft.content
            chunk.heading_path = draft.heading_path
            chunk.token_count = len(lexical_features(draft.content))
            chunk.metadata_json = metadata
            chunk.search_text = " ".join([specification.title, *draft.heading_path, draft.content])
            pending_embeddings.append((chunk, chunk.search_text))
    embeddings = embedding_provider.embed_documents(
        [search_text for _, search_text in pending_embeddings]
    )
    for (chunk, _), embedding in zip(pending_embeddings, embeddings, strict=True):
        stored = next(
            (
                item
                for item in chunk.embeddings
                if item.provider == embedding_provider.provider_name
                and item.model == embedding_provider.model_name
            ),
            None,
        )
        if stored is None:
            stored = KnowledgeChunkEmbedding(
                id=uuid5(
                    NAMESPACE_URL,
                    f"{chunk.id}:{embedding_provider.provider_name}:{embedding_provider.model_name}",
                ),
                chunk=chunk,
                provider=embedding_provider.provider_name,
                model=embedding_provider.model_name,
            )
            session.add(stored)
        stored.embedding = embedding
    session.commit()
    return len(specifications), len(pending_embeddings)
