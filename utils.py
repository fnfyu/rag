"""Small PostgreSQL repository layer used by the API routers."""

import json
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2

from config import settings


class DatabaseNotConfigured(RuntimeError):
    """Raised when an endpoint needs PostgreSQL but DATABASE_URL is absent."""


@contextmanager
def get_db_connection() -> Iterator[Any]:
    if not settings.database_url:
        raise DatabaseNotConfigured("DATABASE_URL is not configured. Copy .env.example to .env first.")

    connection = psycopg2.connect(settings.database_url)
    try:
        yield connection
    finally:
        connection.close()


def get_collection_name_from_db(conversation_id: str) -> str:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT kb.collection_name FROM conversations c JOIN knowledge_bases kb ON kb.id = c.knowledge_base_id WHERE c.id = %s",
            (conversation_id,),
        )
        result = cursor.fetchone()

    if not result:
        raise ValueError(f"Conversation '{conversation_id}' does not exist")
    return result[0]


def get_knowledge_base_id_from_db(conversation_id: str) -> str:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT knowledge_base_id FROM conversations WHERE id = %s", (conversation_id,))
        row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Conversation '{conversation_id}' does not exist")
    return row[0]


def insert_conversation_to_db(
    conversation_id: str, title: str, collection_name: str | None = None,
    knowledge_base_id: str | None = None,
) -> dict[str, Any]:
    """Create a conversation in an existing KB, or create both for the old UI."""
    with get_db_connection() as connection, connection.cursor() as cursor:
        if knowledge_base_id is None:
            knowledge_base_id = f"kb_{uuid.uuid4().hex}"
            collection_name = collection_name or f"kb_collection_{uuid.uuid4().hex}"
            cursor.execute(
                "INSERT INTO knowledge_bases (id, title, collection_name) VALUES (%s, %s, %s)",
                (knowledge_base_id, title, collection_name),
            )
        else:
            cursor.execute("SELECT collection_name FROM knowledge_bases WHERE id = %s", (knowledge_base_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Knowledge base '{knowledge_base_id}' does not exist")
            collection_name = row[0]
        cursor.execute(
            "INSERT INTO conversations (id, title, collection_name, knowledge_base_id) VALUES (%s, %s, %s, %s) RETURNING created_at, updated_at",
            (conversation_id, title, collection_name, knowledge_base_id),
        )
        timestamps = cursor.fetchone()
        connection.commit()
        return {"id": conversation_id, "title": title, "collection_name": collection_name,
                "knowledge_base_id": knowledge_base_id, "created_at": timestamps[0], "updated_at": timestamps[1]}


def get_all_conversations(knowledge_base_id: str | None = None) -> list[tuple[Any, ...]]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, title, updated_at, knowledge_base_id FROM conversations "
            "WHERE (%s IS NULL OR knowledge_base_id = %s) ORDER BY updated_at DESC",
            (knowledge_base_id, knowledge_base_id),
        )
        return cursor.fetchall()


def get_messages_from_conversation(conversation_id: str) -> list[tuple[Any, ...]]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, role, content, sources, citation_validation, retrieval_trace, created_at
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        )
        return cursor.fetchall()


def insert_message_to_db(
    conversation_id: str,
    role: str,
    content: str,
    sources: list[dict[str, Any]] | None,
    citation_validation: dict[str, Any] | None = None,
    retrieval_trace: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, sources, citation_validation, retrieval_trace)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
            """,
            (
                message_id or f"msg_{uuid.uuid4().hex}",
                conversation_id,
                role,
                content,
                json.dumps(sources or []),
                json.dumps(citation_validation or {}),
                json.dumps(retrieval_trace or {}),
            ),
        )
        cursor.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (conversation_id,))
        connection.commit()


def save_file_record_to_db(
    conversation_id: str | None, filename: str, file_path: str, chunk_count: int,
    knowledge_base_id: str | None = None, document_version_id: str | None = None,
) -> None:
    """Append a version's upload record; never delete same-name historical files."""
    with get_db_connection() as connection, connection.cursor() as cursor:
        if knowledge_base_id is None and conversation_id:
            cursor.execute("SELECT knowledge_base_id FROM conversations WHERE id = %s", (conversation_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Conversation '{conversation_id}' does not exist")
            knowledge_base_id = row[0]
        existing = None
        if document_version_id:
            cursor.execute("SELECT id FROM document_versions WHERE id = %s FOR UPDATE", (document_version_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Document version '{document_version_id}' does not exist")
            cursor.execute("SELECT id FROM uploaded_files WHERE document_version_id = %s LIMIT 1", (document_version_id,))
            existing = cursor.fetchone()
        if existing:
            cursor.execute("UPDATE uploaded_files SET chunk_count = %s WHERE id = %s", (chunk_count, existing[0]))
        else:
            cursor.execute(
                "INSERT INTO uploaded_files (id, conversation_id, filename, file_path, file_type, chunk_count, knowledge_base_id, document_version_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (f"file_{uuid.uuid4().hex}", conversation_id, filename, file_path,
                 filename.rsplit(".", maxsplit=1)[-1].lower() if "." in filename else "unknown",
                 chunk_count, knowledge_base_id, document_version_id),
            )
        connection.commit()


def get_files_for_conversation(conversation_id: str) -> list[dict[str, Any]]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT f.id, f.filename, f.file_type, f.chunk_count, f.created_at,
                   f.knowledge_base_id, f.document_version_id, v.version_label, v.release_date, v.applicability, v.status
            FROM uploaded_files f
            JOIN conversations c ON c.knowledge_base_id = f.knowledge_base_id
            LEFT JOIN document_versions v ON v.id = f.document_version_id
            WHERE c.id = %s
            ORDER BY f.created_at DESC
            """,
            (conversation_id,),
        )
        rows = cursor.fetchall()

    return [
        {"id": row[0], "filename": row[1], "file_type": row[2], "chunk_count": row[3], "created_at": row[4],
         "knowledge_base_id": row[5], "document_version_id": row[6], "version_label": row[7],
         "release_date": row[8], "applicability": row[9], "status": row[10]}
        for row in rows
    ]
