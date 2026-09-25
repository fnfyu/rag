"""Conversation and knowledge-base metadata endpoints."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from security import require_api_key
from utils import (
    DatabaseNotConfigured,
    get_all_conversations,
    get_files_for_conversation,
    get_messages_from_conversation,
    insert_conversation_to_db,
)

router = APIRouter(prefix="/conversations", tags=["conversations"], dependencies=[Depends(require_api_key)])


class CreateConversationRequest(BaseModel):
    title: str = Field(default="新知识库", min_length=1, max_length=80)


def _service_unavailable(_: DatabaseNotConfigured) -> HTTPException:
    return HTTPException(status_code=503, detail="数据库服务未配置，请先设置 DATABASE_URL。")


@router.post("", status_code=201)
@router.post("/create", status_code=201)  # Backward-compatible route for the original client.
async def create_conversation(payload: CreateConversationRequest) -> dict[str, str]:
    conversation_id = f"conv_{uuid.uuid4().hex}"
    collection_name = f"kb_{uuid.uuid4().hex}"
    try:
        # Create metadata first. Chroma creates the collection lazily when it receives indexed content.
        await asyncio.to_thread(insert_conversation_to_db, conversation_id, payload.title.strip(), collection_name)
    except DatabaseNotConfigured as error:
        raise _service_unavailable(error) from error

    return {"id": conversation_id, "title": payload.title.strip(), "collection_name": collection_name}


@router.get("")
@router.get("/list")  # Backward-compatible route for the original client.
async def list_conversations() -> list[dict[str, Any]]:
    try:
        rows = await asyncio.to_thread(get_all_conversations)
        return [{"id": row[0], "title": row[1], "updated_at": row[2]} for row in rows]
    except DatabaseNotConfigured as error:
        raise _service_unavailable(error) from error


@router.get("/{conversation_id}/messages")
@router.get("/list/{conversation_id}")  # Backward-compatible route for the original client.
async def load_conversation(conversation_id: str) -> list[dict[str, Any]]:
    try:
        rows = await asyncio.to_thread(get_messages_from_conversation, conversation_id)
    except DatabaseNotConfigured as error:
        raise _service_unavailable(error) from error

    return [
        {
            "id": row[0],
            "role": row[1],
            "parts": [{"type": "text", "text": row[2]}],
            "sources": row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]"),
            "citationValidation": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
            "retrievalTrace": row[5] if isinstance(row[5], dict) else json.loads(row[5] or "{}"),
            "created_at": row[6],
        }
        for row in rows
    ]


@router.get("/{conversation_id}/documents")
async def list_documents(conversation_id: str) -> list[dict[str, Any]]:
    try:
        return await asyncio.to_thread(get_files_for_conversation, conversation_id)
    except DatabaseNotConfigured as error:
        raise _service_unavailable(error) from error
