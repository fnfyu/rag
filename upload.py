"""Safe upload endpoint with an observable indexing lifecycle."""

import asyncio
from datetime import datetime, timezone
import logging
import uuid
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile

from backend import get_rag_service
from config import settings
from security import require_api_key
from utils import DatabaseNotConfigured, get_collection_name_from_db, save_file_record_to_db

router = APIRouter(prefix="/uploads", tags=["uploads"], dependencies=[Depends(require_api_key)])

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".csv", ".json", ".py", ".log"}
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


def _list_tasks(conversation_id: str | None = None) -> list[dict[str, Any]]:
    with _upload_lock:
        tasks = list(_upload_tasks.values())
    if conversation_id:
        tasks = [task for task in tasks if task.get("conversation_id") == conversation_id]
    return [dict(task) for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True)]


@router.post("", status_code=202)
@router.post("/upload", status_code=202)  # Backward-compatible route for the original client.
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
) -> dict[str, Any]:
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if not filename or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    try:
        await asyncio.to_thread(get_collection_name_from_db, conversation_id)
    except DatabaseNotConfigured as error:
        raise HTTPException(status_code=503, detail="数据库服务未配置，请先设置 DATABASE_URL。") from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

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

    source_id = f"{conversation_id}:{filename.casefold()}"
    created_at = _now()
    _set_task(
        upload_id,
        id=upload_id,
        conversation_id=conversation_id,
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
    background_tasks.add_task(_index_upload, destination, upload_id, conversation_id, filename, source_id)
    return {"upload_id": upload_id, "filename": filename, "status": "queued", "message": "文件已进入索引队列。"}


def _index_upload(path: Path, upload_id: str, conversation_id: str, filename: str, source_id: str) -> None:
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
            status="completed" if stage == "ready" else "processing",
            stage=stage,
            stage_label=labels.get(stage, stage),
            stage_index=index,
            stage_total=STAGE_TOTAL,
            progress=100 if stage == "ready" else None,
        )

    try:
        collection_name = get_collection_name_from_db(conversation_id)
        chunk_count = get_rag_service().index_document(
            path,
            collection_name,
            source_id,
            filename,
            progress_callback=report,
        )
        save_file_record_to_db(conversation_id, filename, str(path), chunk_count)
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
async def list_upload_status(conversation_id: str | None = Query(default=None)) -> list[dict[str, Any]]:
    """List active-process indexing jobs so the UI can recover after navigation."""
    return _list_tasks(conversation_id)


@router.get("/{upload_id}")
@router.get("/status/{upload_id}")
async def get_upload_status(upload_id: str) -> dict[str, Any]:
    task = _get_task(upload_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Upload task was not found. Status is retained only for the active server process.")
    return task
