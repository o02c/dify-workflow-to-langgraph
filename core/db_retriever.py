"""Database retriever module for Dify's PGVector knowledge base.

This module provides connection and retrieval functionality for
Dify's existing RDS (PostgreSQL with PGVector extension).
"""

import os
from dataclasses import dataclass
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class RetrievalResult:
    """Represents a single retrieval result from the knowledge base.

    Attributes:
        id: Document segment ID.
        content: The text content of the segment.
        score: Similarity score (lower is more similar for L2 distance).
        metadata: Additional metadata associated with the segment.
    """

    id: str
    content: str
    score: float
    metadata: dict[str, Any]


class DifyPGVectorRetriever:
    """Retriever for Dify's PGVector-based knowledge base.

    Connects to Dify's existing RDS instance and performs similarity
    search using the pgvector extension.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        """Initialize the retriever with database connection parameters.

        If parameters are not provided, they are read from environment variables:
        - DIFY_DB_HOST
        - DIFY_DB_PORT
        - DIFY_DB_NAME
        - DIFY_DB_USER
        - DIFY_DB_PASSWORD

        Args:
            host: Database host address.
            port: Database port number.
            database: Database name.
            user: Database user.
            password: Database password.
        """
        self.host = host or os.environ.get("DIFY_DB_HOST", "localhost")
        self.port = port or int(os.environ.get("DIFY_DB_PORT", "5432"))
        self.database = database or os.environ.get("DIFY_DB_NAME", "dify")
        self.user = user or os.environ.get("DIFY_DB_USER", "postgres")
        self.password = password or os.environ.get("DIFY_DB_PASSWORD", "")
        self._conn = None

    def _get_connection(self):
        """Get or create a database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
        return self._conn

    def close(self):
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def retrieve(
        self,
        query_embedding: list[float],
        dataset_id: str,
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve similar documents from the knowledge base.

        Args:
            query_embedding: The embedding vector for the query.
            dataset_id: The Dify dataset ID to search within.
            top_k: Maximum number of results to return.
            score_threshold: Optional threshold to filter results by similarity.

        Returns:
            List of RetrievalResult objects sorted by similarity.
        """
        conn = self._get_connection()

        # Dify stores embeddings in the 'embeddings' table
        # with references to 'dataset_document_segments' for content
        query = """
            SELECT
                e.id,
                s.content,
                e.embedding <-> %s::vector AS distance,
                s.keywords,
                s.index_node_hash,
                d.name AS document_name
            FROM embeddings e
            JOIN dataset_document_segments s ON e.segment_id = s.id
            JOIN dataset_documents d ON s.document_id = d.id
            WHERE s.dataset_id = %s
            AND s.status = 'completed'
            AND s.enabled = true
            ORDER BY e.embedding <-> %s::vector
            LIMIT %s
        """

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            embedding_str = f"[{','.join(map(str, query_embedding))}]"
            cur.execute(query, (embedding_str, dataset_id, embedding_str, top_k))
            rows = cur.fetchall()

        results = []
        for row in rows:
            score = float(row["distance"])
            if score_threshold is not None and score > score_threshold:
                continue

            results.append(
                RetrievalResult(
                    id=str(row["id"]),
                    content=row["content"],
                    score=score,
                    metadata={
                        "keywords": row.get("keywords"),
                        "document_name": row.get("document_name"),
                        "index_node_hash": row.get("index_node_hash"),
                    },
                )
            )

        return results

    def retrieve_by_text(
        self,
        query_text: str,
        dataset_id: str,
        embedding_model: Any,
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve similar documents using a text query.

        This is a convenience method that generates an embedding from
        the query text before performing similarity search.

        Args:
            query_text: The text query to search for.
            dataset_id: The Dify dataset ID to search within.
            embedding_model: An embedding model with an embed_query method.
            top_k: Maximum number of results to return.
            score_threshold: Optional threshold to filter results by similarity.

        Returns:
            List of RetrievalResult objects sorted by similarity.
        """
        query_embedding = embedding_model.embed_query(query_text)
        return self.retrieve(
            query_embedding=query_embedding,
            dataset_id=dataset_id,
            top_k=top_k,
            score_threshold=score_threshold,
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
