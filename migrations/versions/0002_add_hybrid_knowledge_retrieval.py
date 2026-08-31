"""Add pgvector-backed hybrid knowledge retrieval.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("product_version", sa.String(length=50), nullable=True),
        sa.Column("applicable_plans", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authority", sa.String(length=30), nullable=False),
        sa.Column("data_origin", sa.String(length=20), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("license", sa.String(length=100), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "authority IN ('official', 'synthetic_ticket', 'public_reference')",
            name=op.f("ck_knowledge_documents_valid_authority"),
        ),
        sa.CheckConstraint(
            "data_origin IN ('synthetic', 'human_labeled', 'public')",
            name=op.f("ck_knowledge_documents_valid_data_origin"),
        ),
        sa.CheckConstraint(
            "doc_type IN ('guide', 'api_reference', 'faq', 'known_issue', 'runbook', "
            "'release_note', 'ticket_resolution')",
            name=op.f("ck_knowledge_documents_valid_doc_type"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'superseded', 'archived')",
            name=op.f("ck_knowledge_documents_valid_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint("source_uri", name=op.f("uq_knowledge_documents_source_uri")),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("heading_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, search_text)", persisted=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_knowledge_chunk_ordinal"),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_document_id"),
        "knowledge_chunks",
        ["document_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_search_vector",
        "knowledge_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_table(
        "knowledge_chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("embedding", VECTOR(dim=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["knowledge_chunks.id"],
            name=op.f("fk_knowledge_chunk_embeddings_chunk_id_knowledge_chunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunk_embeddings")),
        sa.UniqueConstraint("chunk_id", "provider", "model", name="uq_chunk_embedding_model"),
    )
    op.create_index(
        op.f("ix_knowledge_chunk_embeddings_chunk_id"),
        "knowledge_chunk_embeddings",
        ["chunk_id"],
    )
    op.create_index(
        "ix_knowledge_chunk_embeddings_hnsw",
        "knowledge_chunk_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_chunk_embeddings_hnsw",
        table_name="knowledge_chunk_embeddings",
    )
    op.drop_index(
        op.f("ix_knowledge_chunk_embeddings_chunk_id"),
        table_name="knowledge_chunk_embeddings",
    )
    op.drop_table("knowledge_chunk_embeddings")
    op.drop_index("ix_knowledge_chunks_search_vector", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
