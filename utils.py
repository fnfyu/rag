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
        cursor.execute("SELECT collection_name FROM conversations WHERE id = %s", (conversation_id,))
        result = cursor.fetchone()

    if not result:
        raise ValueError(f"Conversation '{conversation_id}' does not exist")
    return result[0]


def insert_conversation_to_db(conversation_id: str, title: str, collection_name: str) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO conversations (id, title, collection_name)
            VALUES (%s, %s, %s)
            """,
            (conversation_id, title, collection_name),
        )
        connection.commit()


def get_all_conversations() -> list[tuple[Any, ...]]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, title, updated_at
            FROM conversations
            ORDER BY updated_at DESC
            """
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


def save_file_record_to_db(conversation_id: str, filename: str, file_path: str, chunk_count: int) -> None:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM uploaded_files WHERE conversation_id = %s AND LOWER(filename) = LOWER(%s)",
            (conversation_id, filename),
        )
        cursor.execute(
            """
            INSERT INTO uploaded_files (id, conversation_id, filename, file_path, file_type, chunk_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                f"file_{uuid.uuid4().hex}",
                conversation_id,
                filename,
                file_path,
                filename.rsplit(".", maxsplit=1)[-1].lower() if "." in filename else "unknown",
                chunk_count,
            ),
        )
        connection.commit()


def get_files_for_conversation(conversation_id: str) -> list[dict[str, Any]]:
    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, filename, file_type, chunk_count, created_at
            FROM uploaded_files
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            """,
            (conversation_id,),
        )
        rows = cursor.fetchall()

    return [
        {"id": row[0], "filename": row[1], "file_type": row[2], "chunk_count": row[3], "created_at": row[4]}
        for row in rows
    ]
