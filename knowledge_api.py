"""Knowledge-base routes. Research-task execution lives in the research router."""

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from security import require_api_key
from utils import DatabaseNotConfigured, get_all_conversations, insert_conversation_to_db
import workspace_store as store

router = APIRouter(prefix='/knowledge-bases', tags=['knowledge-bases'], dependencies=[Depends(require_api_key)])


class CreateKnowledgeBaseRequest(BaseModel):
    title: str = Field(default='新知识库', min_length=1, max_length=80)
    description: str = ''
    game_profile: dict[str, Any] = Field(default_factory=dict)


class CreateConversationRequest(BaseModel):
    title: str = Field(default='新会话', min_length=1, max_length=80)


class CreateTaskRequest(BaseModel):
    title: str = Field(default='新研究任务', min_length=1, max_length=200)
    question: str = ''
    outline: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


async def _call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except DatabaseNotConfigured as error:
        raise HTTPException(status_code=503, detail='数据库服务未配置，请先设置 DATABASE_URL。') from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def _require_knowledge_base(knowledge_base_id: str) -> dict[str, Any]:
    record = await _call(store.get_knowledge_base, knowledge_base_id)
    if record is None:
        raise HTTPException(status_code=404, detail='Knowledge base does not exist')
    return record


@router.get('')
async def list_knowledge_bases() -> list[dict[str, Any]]:
    return await _call(store.list_knowledge_bases)


@router.post('', status_code=201)
async def create_knowledge_base(payload: CreateKnowledgeBaseRequest) -> dict[str, Any]:
    return await _call(store.create_knowledge_base, payload.title, payload.description, payload.game_profile)


@router.get('/{knowledge_base_id}')
async def get_knowledge_base(knowledge_base_id: str) -> dict[str, Any]:
    return await _require_knowledge_base(knowledge_base_id)


@router.patch('/{knowledge_base_id}/game-profile')
async def update_game_profile(knowledge_base_id: str, profile: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Body is the profile object; return its normalized replacement."""
    await _require_knowledge_base(knowledge_base_id)
    record = await _call(store.update_game_profile, knowledge_base_id, profile)
    return record['game_profile']


@router.patch('/{knowledge_base_id}/documents/{version_id}/metadata')
async def update_document_metadata(knowledge_base_id: str, version_id: str,
                                   metadata: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Body is domain_metadata; official tier stays a manual declaration."""
    await _require_knowledge_base(knowledge_base_id)
    version = await _call(store.get_document_version, version_id)
    if version is None or version['knowledge_base_id'] != knowledge_base_id:
        raise HTTPException(status_code=404, detail='Document version does not exist in this knowledge base')
    return await _call(store.update_document_metadata, version_id, metadata)


@router.get('/{knowledge_base_id}/conversations')
async def list_conversations(knowledge_base_id: str) -> list[dict[str, Any]]:
    await _require_knowledge_base(knowledge_base_id)
    rows = await _call(get_all_conversations, knowledge_base_id)
    return [{'id': row[0], 'title': row[1], 'updated_at': row[2], 'knowledge_base_id': row[3]} for row in rows]


@router.post('/{knowledge_base_id}/conversations', status_code=201)
async def create_conversation(knowledge_base_id: str, payload: CreateConversationRequest) -> dict[str, Any]:
    await _require_knowledge_base(knowledge_base_id)
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail='Conversation title is required')
    return await _call(insert_conversation_to_db, f'conv_{uuid.uuid4().hex}', payload.title.strip(), knowledge_base_id=knowledge_base_id)


@router.get('/{knowledge_base_id}/tasks')
async def list_tasks(knowledge_base_id: str) -> list[dict[str, Any]]:
    await _require_knowledge_base(knowledge_base_id)
    return await _call(store.list_research_tasks, knowledge_base_id)


@router.post('/{knowledge_base_id}/tasks', status_code=201)
async def create_task(knowledge_base_id: str, payload: CreateTaskRequest) -> dict[str, Any]:
    await _require_knowledge_base(knowledge_base_id)
    return await _call(store.create_research_task, knowledge_base_id, payload.title, payload.question, payload.outline, payload.context)


@router.get('/{knowledge_base_id}/documents')
async def list_documents(knowledge_base_id: str) -> list[dict[str, Any]]:
    """All series and versions; ordering does not imply version applicability."""
    await _require_knowledge_base(knowledge_base_id)
    return await _call(store.list_document_series, knowledge_base_id)
