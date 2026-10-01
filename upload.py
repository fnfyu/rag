"""Safe upload endpoint with an observable indexing lifecycle."""

import asyncio
from datetime import date, datetime, timezone
import hashlib
import json
import logging
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile

from backend import get_rag_service
from config import settings
from security import require_api_key
from souls_domain import normalize_metadata
from utils import DatabaseNotConfigured, get_knowledge_base_id_from_db, save_file_record_to_db
from workspace_store import (
    create_document_version, get_knowledge_base, resolve_document_version, update_document_version,
)

router = APIRouter(prefix="/uploads", tags=["uploads"], dependencies=[Depends(require_api_key)])

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".csv", ".json", ".py", ".log", ".png", ".jpg", ".jpeg", ".webp"}
COPY_CHUNK_SIZE = 1024 * 1024
STAGE_TOTAL = 5
logger = logging.getLogger(__name__)


class UploadTooLargeError(RuntimeError):
    """Raised when a streamed upload exceeds the configured compressed-size limit."""


def _save_upload_stream(source: Any, destination: Path, max_bytes: int) -> int:
    bytes_written = 0
    with destination.open("wb") as target:
        while chunk := source.read(COPY_CHUNK_SIZE):
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                raise UploadTooLargeError
            target.write(chunk)
    return bytes_written


_upload_tasks: dict[str, dict[str, Any]] = {}
_upload_lock = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_task(upload_id: str, **updates: Any) -> None:
    with _upload_lock:
        task = _upload_tasks.setdefault(upload_id, {"id": upload_id, "events": []})
        previous_stage = task.get("stage")
        previous_status = task.get("status")
        task.update(updates)
        timestamp = _now()
        task["updated_at"] = timestamp
        stage = task.get("stage")
        if stage:
            # The lifecycle contract exposes when each stage was first observed.
            task.setdefault("stage_timestamps", {}).setdefault(str(stage), timestamp)
        if previous_stage != task.get("stage") or previous_status != task.get("status"):
            events = task.setdefault("events", [])
            events.append(
                {
                    "at": timestamp,
                    "stage": task.get("stage"),
                    "status": task.get("status"),
                    "message": task.get("stage_label"),
                }
            )
            del events[:-20]


def _get_task(upload_id: str) -> dict[str, Any] | None:
    with _upload_lock:
        task = _upload_tasks.get(upload_id)
        return dict(task) if task else None


def _list_tasks(conversation_id: str | None = None, knowledge_base_id: str | None = None) -> list[dict[str, Any]]:
    with _upload_lock:
        tasks = list(_upload_tasks.values())
    if conversation_id:
        tasks = [task for task in tasks if task.get("conversation_id") == conversation_id]
    if knowledge_base_id:
        tasks = [task for task in tasks if task.get("knowledge_base_id") == knowledge_base_id]
    return [dict(task) for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


@router.post("", status_code=202)
@router.post("/upload", status_code=202)  # Backward-compatible route for the original client.
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    knowledge_base_id: str | None = Form(default=None),
    version_label: str | None = Form(default=None),
    release_date: str | None = Form(default=None),
    applicability: str | None = Form(default=None),
    domain_metadata: str | None = Form(default=None),
) -> dict[str, Any]:
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if not filename or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    if not conversation_id and not knowledge_base_id:
        raise HTTPException(status_code=422, detail="conversation_id 或 knowledge_base_id 至少提供一个。")
    if release_date:
        try:
            release_date = date.fromisoformat(release_date).isoformat()
        except ValueError as error:
            raise HTTPException(status_code=422, detail="release_date 应为 YYYY-MM-DD。") from error
    else:
        release_date = None
    applicability_value: dict | str | None = applicability
    if applicability:
        try:
            decoded = json.loads(applicability)
            if isinstance(decoded, dict):
                applicability_value = decoded
        except json.JSONDecodeError:
            pass  # Free-text applicability is a valid domain value.
    try:
        if conversation_id:
            conversation_kb = await asyncio.to_thread(get_knowledge_base_id_from_db, conversation_id)
            if knowledge_base_id and knowledge_base_id != conversation_kb:
                raise HTTPException(status_code=422, detail="会话不属于指定知识库。")
            knowledge_base_id = conversation_kb
        knowledge_base = await asyncio.to_thread(get_knowledge_base, knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="Knowledge base does not exist")
    except DatabaseNotConfigured as error:
        raise HTTPException(status_code=503, detail="数据库服务未配置，请先设置 DATABASE_URL。") from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    try:
        metadata_value = json.loads(domain_metadata) if domain_metadata else {}
        metadata_value = normalize_metadata(metadata_value, knowledge_base.get('game_profile') or {}, manual=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    settings.ensure_storage_directories()
    upload_id = f"upload_{uuid.uuid4().hex}"
    destination = settings.upload_dir / f"{upload_id}{extension}"
    try:
        size = await asyncio.to_thread(
            _save_upload_stream,
            file.file,
            destination,
            settings.max_upload_size_mb * 1024 * 1024,
        )
    except UploadTooLargeError as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_size_mb} MB limit") from error
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    try:
        sha256 = await asyncio.to_thread(_sha256, destination)
        version = await asyncio.to_thread(
            create_document_version, knowledge_base_id, filename, str(destination), sha256,
            version_label, release_date, applicability_value, domain_metadata=metadata_value,
        )
        private_version = await asyncio.to_thread(resolve_document_version, version['id'])
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    reused = private_version['file_path'] != str(destination)
    if reused:
        destination.unlink(missing_ok=True)
        # If an identical version is already being indexed, return its live job.
        active = next((task for task in _list_tasks(knowledge_base_id=knowledge_base_id)
                       if task.get('document_version_id') == version['id'] and task.get('status') in {'queued', 'processing'}), None)
        if active:
            return {**active, 'upload_id': active['id'], 'version': version, 'reused': True,
                    'message': '相同资料版本已在索引队列中。'}
    destination = Path(private_version['file_path'])
    source_id = version['source_id']
    ready = version['status'] == 'ready'
    created_at = _now()
    _set_task(
        upload_id,
        id=upload_id,
        conversation_id=conversation_id,
        knowledge_base_id=knowledge_base_id,
        document_series_id=version['document_series_id'],
        document_version_id=version['id'],
        source_id=source_id,
        version_label=version['version_label'],
        release_date=version['release_date'],
        applicability=version['applicability'],
        domain_metadata=version.get('domain_metadata', {}),
        sha256=sha256,
        reused=reused,
        filename=filename,
        size=size,
        mime=file.content_type or "application/octet-stream",
        status="queued",
        stage="queued",
        stage_label="等待索引",
        stage_index=0,
        stage_total=STAGE_TOTAL,
        progress=None,
        chunk_count=None,
        indexed_count=0,
        error_code=None,
        error=None,
        retryable=True,
        created_at=created_at,
        updated_at=created_at,
    )
    if ready:
        _set_task(upload_id, status='completed', stage='ready', stage_label='可检索',
                  stage_index=STAGE_TOTAL, progress=100, chunk_count=version['chunk_count'],
                  indexed_count=version['chunk_count'], retryable=False)
    else:
        background_tasks.add_task(_index_upload, destination, upload_id, conversation_id, filename, source_id,
                                  knowledge_base['collection_name'], version)
    return {"upload_id": upload_id, "filename": filename, "status": "completed" if ready else "queued",
            "knowledge_base_id": knowledge_base_id, "document_series_id": version['document_series_id'],
            "document_version_id": version['id'], "version": version, "reused": reused,
            "message": "复用相同资料版本。" if ready else "文件版本已进入索引队列；上传顺序不代表适用性。"}


def _index_upload(
    path: Path, upload_id: str, conversation_id: str | None, filename: str,
    source_id: str, collection_name: str, version: dict[str, Any],
) -> None:
    _set_task(upload_id, status="processing", stage="parsing", stage_label="解析资料", stage_index=1, progress=None)

    def report(stage: str, index: int) -> None:
        labels = {
            "parsing": "解析资料",
            "chunking": "切分片段",
            "embedding": "生成向量",
            "persisting": "写入索引",
            "ready": "可检索",
        }
        _set_task(
            upload_id,
            status="processing",  # Completed only after version/upload metadata commit.
            stage=stage,
            stage_label=labels.get(stage, stage),
            stage_index=index,
            stage_total=STAGE_TOTAL,
            progress=100 if stage == "ready" else None,
        )

    try:
        source_metadata = {key: version.get(key) for key in (
            'knowledge_base_id', 'document_series_id', 'version_label', 'release_date', 'applicability',
        )}
        source_metadata['document_version_id'] = version['id']
        metadata = version.get('domain_metadata') or {}
        source_metadata['domain_metadata'] = metadata
        for key, flat in {'game_id': 'game_id', 'edition': 'game_edition', 'patch': 'game_patch',
                          'dlc': 'game_dlc', 'platform': 'game_platform', 'mode': 'game_mode',
                          'source_kind': 'source_kind', 'source_tier': 'source_tier', 'source_url': 'source_url',
                          'captured_at': 'captured_at', 'published_at': 'published_at', 'provenance': 'provenance',
                          'requires_dlc': 'requires_dlc', 'content_sha256': 'content_sha256',
                          'capture_sha256': 'capture_sha256'}.items():
            if key in metadata:
                source_metadata[flat] = metadata[key]
        chunk_count = get_rag_service().index_document(
            path,
            collection_name,
            source_id,
            filename,
            progress_callback=report,
            source_metadata=source_metadata,
        )
        save_file_record_to_db(conversation_id, filename, str(path), chunk_count,
                               version['knowledge_base_id'], version['id'])
        update_document_version(version['id'], 'ready', chunk_count=chunk_count)
        _set_task(
            upload_id,
            status="completed",
            stage="ready",
            stage_label="可检索",
            stage_index=STAGE_TOTAL,
            stage_total=STAGE_TOTAL,
            progress=100,
            chunk_count=chunk_count,
            indexed_count=chunk_count,
            error_code=None,
            error=None,
            retryable=False,
        )
    except Exception:
        logger.exception("document indexing failed for upload %s", upload_id)
        try:
            update_document_version(version['id'], 'error', error='文档索引失败，请检查模型与解析器配置。')
        except Exception:
            logger.exception('could not persist failed version status for %s', version['id'])
        previous = _get_task(upload_id) or {}
        _set_task(
            upload_id,
            status="failed",
            stage="error",
            failed_stage=previous.get("stage"),
            stage_label="索引失败",
            error_code="indexing_failed",
            error="文档索引失败，请检查模型与解析器配置。",
            retryable=True,
        )


@router.get("")
async def list_upload_status(
    conversation_id: str | None = Query(default=None),
    knowledge_base_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List live jobs; durable queued/ready/error states live on document versions."""
    return _list_tasks(conversation_id, knowledge_base_id)


@router.get("/{upload_id}")
@router.get("/status/{upload_id}")
async def get_upload_status(upload_id: str) -> dict[str, Any]:
    task = _get_task(upload_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Upload task was not found. Status is retained only for the active server process.")
    return task
