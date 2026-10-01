"""Research tasks: confirmed outlines, resumable delivery and immutable report history."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from starlette.responses import Response

from backend import get_rag_service
from claim_audit import audit_answer
from citations import validate_citations
from reporting import ACTIVE_TASKS, ReportWorkspace, now, outline_signature, propose_outline, report_diff, report_html, report_markdown
from security import require_api_key
from utils import DatabaseNotConfigured
import workspace_store as store

router = APIRouter(prefix="/research-tasks", tags=["research-delivery"], dependencies=[Depends(require_api_key)])


async def call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except DatabaseNotConfigured as error:
        raise HTTPException(status_code=503, detail="请配置数据库并执行第二版数据库初始化脚本。") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def require_task(task_id: str) -> dict:
    task = await call(store.get_research_task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    return {**task, "active": task_id in ACTIVE_TASKS}


def editable(task_id: str) -> None:
    if task_id in ACTIVE_TASKS:
        raise HTTPException(status_code=409, detail="该任务正在研究，请等待本轮完成后编辑或修订。")


@router.get("")
async def list_tasks(knowledge_base_id: str | None = None) -> list[dict]:
    tasks = await call(store.list_research_tasks, knowledge_base_id)
    return [{**task, "active": task["id"] in ACTIVE_TASKS} for task in tasks]


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    return await require_task(task_id)


@router.patch("/{task_id}")
async def edit_task(task_id: str, body: dict[str, Any] = Body(...)) -> dict:
    editable(task_id)
    task = await require_task(task_id)
    updates = {key: body[key] for key in ("title", "question", "outline", "context") if key in body}
    if "context" in updates:
        updates["context"] = {**task.get("context", {}), **updates["context"]}
    if "outline" in updates:
        identifiers = [item.get("id") for item in updates["outline"] if item.get("id")]
        if len(identifiers) != len(set(identifiers)):
            raise HTTPException(status_code=422, detail="章节ID不能重复")
        if len(updates["outline"]) > get_rag_service().settings.report_max_sections:
            raise HTTPException(status_code=422, detail="提纲超过配置的最大章节数")
    return await call(store.update_research_task, task_id, **updates)


@router.post("/{task_id}/outline")
async def generate_outline(task_id: str) -> dict:
    editable(task_id)
    task = await require_task(task_id)
    if not task.get("question", "").strip():
        raise HTTPException(status_code=422, detail="请先填写研究目标")
    try:
        outline = await propose_outline(task, get_rag_service())
    except Exception as error:
        raise HTTPException(status_code=503, detail="提纲生成未完成，请检查文本模型配置；也可以直接手工编辑提纲。") from error
    if not outline:
        raise HTTPException(status_code=422, detail="未生成有效提纲，请明确研究范围")
    return await call(store.update_research_task, task_id, outline=outline, status="draft")


async def _worker(task_id: str, **kwargs: Any) -> None:
    try:
        await ReportWorkspace(get_rag_service()).run(task_id, **kwargs)
    finally:
        ACTIVE_TASKS.discard(task_id)


async def launch(task_id: str, background: BackgroundTasks, *, section_ids: list[str] | None = None,
                 resume: bool = True, revision_request: dict | None = None) -> dict:
    editable(task_id)
    task = await require_task(task_id)
    enabled = [item for item in task.get("outline", []) if item.get("enabled", True)]
    if not enabled or any(not item.get("title", "").strip() for item in enabled):
        raise HTTPException(status_code=422, detail="请先确认包含有效章节的研究提纲")
    if len(enabled) > get_rag_service().settings.report_max_sections:
        raise HTTPException(status_code=422, detail="提纲超过最大章节数")
    if section_ids is not None and (not section_ids or set(section_ids) - {item["id"] for item in enabled}):
        raise HTTPException(status_code=422, detail="请选择提纲中的有效章节")
    context = deepcopy(task.get("context") or {})
    if not resume:
        context.pop("draft_report", None)
    context["progress"] = {"stage": "queued", "message": "研究任务已开始", "index": 0, "total": len(enabled), "at": now(), "events": []}
    task = await call(store.update_research_task, task_id, status="running", context=context)
    ACTIVE_TASKS.add(task_id)
    background.add_task(_worker, task_id, section_ids=section_ids, resume=resume, revision_request=revision_request)
    return {**task, "active": True}


@router.post("/{task_id}/run", status_code=202)
async def run_task(task_id: str, background_tasks: BackgroundTasks, body: dict = Body(default={})) -> dict:
    return await launch(task_id, background_tasks, section_ids=body.get("section_ids"), resume=body.get("resume", True))


@router.post("/{task_id}/revise", status_code=202)
async def revise_chapter(task_id: str, background_tasks: BackgroundTasks, body: dict = Body(...)) -> dict:
    task = await require_task(task_id)
    if not task.get("report"):
        raise HTTPException(status_code=422, detail="请先生成报告，再进行局部修订")
    section_id = body.get("section_id")
    if section_id not in {item["id"] for item in task["report"].get("sections", [])}:
        raise HTTPException(status_code=422, detail="报告章节不存在")
    request = {"instruction": str(body.get("instruction", "")), "claim_ids": body.get("claim_ids") or []}
    # A revision starts from the committed report, never a stale failed-run draft.
    return await launch(task_id, background_tasks, section_ids=[section_id], resume=False, revision_request=request)


@router.post("/{task_id}/sections/{section_id}/edit")
async def edit_chapter(task_id: str, section_id: str, body: dict = Body(...)) -> dict:
    editable(task_id)
    task = await require_task(task_id)
    report = deepcopy(task.get("report"))
    if not report:
        raise HTTPException(status_code=422, detail="报告尚未生成")
    section = next((item for item in report["sections"] if item["id"] == section_id), None)
    if section is None:
        raise HTTPException(status_code=404, detail="报告章节不存在")
    content = body.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(status_code=422, detail="章节正文不能为空")
    # A user may cite any existing report source, not only previously cited ones.
    sources = report.get("sources", [])
    service = get_rag_service()
    audit = await audit_answer(content, sources, service.llm, max_claims=service.settings.claim_audit_max_claims,
                               timeout_seconds=service.settings.claim_audit_timeout_seconds,
                               domain_context=task.get("context", {}).get("game")) if service.settings.claim_audit_enabled and sources and service.settings.ollama_model else {"status": "skipped", "claims": []}
    validation = validate_citations(content, sources)
    old_report = deepcopy(task["report"])
    cited = set(validation["cited_ids"])
    section.update(content=content, audit=audit, citation_validation=validation,
                   sources=[source["id"] for source in sources if source["id"] in cited], updated_at=now())
    section["unresolved"] = [f"{claim['text']}：{claim.get('reason', '')}" for claim in audit.get("claims", []) if claim["verdict"] != "supported"]
    if validation["status"] != "valid":
        section["unresolved"].extend(validation.get("warnings", []))
    section["status"] = "partial" if section["unresolved"] else "completed"
    report.update(revision=task["revision"] + 1, generated_at=now())
    updated = await call(store.save_report_revision, task_id, report, kind="manual", changes=report_diff(old_report, report))
    context = deepcopy(task.get("context", {})); context.pop("draft_report", None)
    await call(store.update_research_task, task_id, context=context,
               status="completed" if all(item["status"] == "completed" for item in report["sections"]) else "partial")
    return await require_task(updated["id"])


@router.get("/{task_id}/versions")
async def report_versions(task_id: str) -> list[dict]:
    await require_task(task_id)
    return await call(store.list_report_revisions, task_id)


@router.get("/{task_id}/versions/{revision}")
async def report_version(task_id: str, revision: int) -> dict:
    await require_task(task_id)
    version = await call(store.get_report_revision, task_id, revision)
    if version is None:
        raise HTTPException(status_code=404, detail="报告版本不存在")
    return version


@router.get("/{task_id}/diff")
async def compare_reports(task_id: str, from_revision: int, to_revision: int) -> dict:
    left, right = await report_version(task_id, from_revision), await report_version(task_id, to_revision)
    return {"from_revision": from_revision, "to_revision": to_revision, "sections": report_diff(left["report"], right["report"])}


@router.post("/{task_id}/restore/{revision}")
async def restore_report(task_id: str, revision: int) -> dict:
    editable(task_id)
    task, version = await require_task(task_id), await report_version(task_id, revision)
    report = deepcopy(version["report"])
    report.update(revision=task["revision"] + 1, generated_at=now())
    updated = await call(store.save_report_revision, task_id, report, kind="restored", changes=report_diff(task.get("report"), report))
    context = deepcopy(task.get("context", {})); context.pop("draft_report", None)
    if "selected_version_ids" in report:
        context["selected_version_ids"] = report["selected_version_ids"]
    context["applicability"] = report.get("applicability")
    context["research_goal"] = report.get("question", task["question"])
    if report.get("game"):
        context["game"] = deepcopy(report["game"])
    else:
        context.pop("game", None)
    context.pop("game_scope", None)
    await call(store.update_research_task, task_id, title=report.get("title", task["title"]),
               question=report.get("question", task["question"]), outline=report.get("outline", task["outline"]), context=context,
               status="completed" if all(item["status"] == "completed" for item in report.get("sections", [])) else "partial")
    return await require_task(updated["id"])


@router.get("/{task_id}/export")
async def export_report(task_id: str, format: str = Query(default="markdown", pattern="^(markdown|html|json)$"),
                        revision: int | None = None) -> Response:
    task = await require_task(task_id)
    report = (await report_version(task_id, revision))["report"] if revision is not None else task.get("report")
    if not report:
        raise HTTPException(status_code=422, detail="报告尚未生成")
    if format == "markdown":
        content, suffix, media_type = report_markdown(report), "md", "text/markdown"
    elif format == "html":
        content, suffix, media_type = report_html(report), "html", "text/html"
    else:
        content, suffix, media_type = json.dumps(report, ensure_ascii=False, indent=2), "json", "application/json"
    filename = f"research-{task_id}-v{report.get('revision', task['revision'])}.{suffix}"
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
