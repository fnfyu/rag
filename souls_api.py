"""Soulsgame workbench: draft guides, preview official news, import and track impact."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query

from backend import get_rag_service
from config import settings
from report_api import call
from security import require_api_key
from souls_domain import catalog, normalize_profile, normalize_metadata, task_payload, templates_for
from souls_impact import patch_impact
from souls_sources import sources_for, fetch_updates, fetch_article, SourceError
from souls_tools import calculate
import workspace_store as store

router = APIRouter(prefix="/games", tags=["souls-guides"], dependencies=[Depends(require_api_key)])
_IMPORTS: dict[str, dict] = {}


def require_game(game_id: str) -> dict:
    game = next((game for game in catalog() if game["id"] == game_id), None)
    if game is None:
        raise HTTPException(status_code=404, detail="不支持的游戏，请从五款游戏档案中选择")
    return game


async def game_knowledge_base(game_id: str, identifier: str) -> dict:
    require_game(game_id)
    kb = await call(store.get_knowledge_base, identifier)
    if kb is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if (kb.get("game_profile") or {}).get("game_id") != game_id:
        raise HTTPException(status_code=422, detail="该知识库未绑定此游戏，请创建独立游戏知识库或确认游戏档案")
    return kb


@router.get("")
async def games() -> list[dict]:
    return catalog()


@router.get("/imports")
async def list_imports(knowledge_base_id: str) -> list[dict]:
    versions = await call(store.list_document_versions, knowledge_base_id)
    return [{"import_id": version["id"], "version_id": version["id"], "title": version.get("domain_metadata", {}).get("title"),
             "status": "completed" if version["status"] == "ready" else "error" if version["status"] == "error" else "queued",
             "active": _IMPORTS.get(version["id"], {}).get("status") in {"queued", "running"}, "knowledge_base_id": knowledge_base_id}
            for version in versions if version.get("domain_metadata", {}).get("provenance") in {"verified_capture", "feed_capture"}]


@router.get("/imports/{import_id}")
async def import_status(import_id: str) -> dict:
    version = await call(store.get_document_version, import_id)
    if version is None:
        raise HTTPException(status_code=404, detail="公告导入记录不存在")
    job = _IMPORTS.get(import_id)
    status = job.get("status") if job else "completed" if version["status"] == "ready" else "error" if version["status"] == "error" else "queued"
    return {"import_id": import_id, "version_id": version["id"], "status": status, "active": bool(job and status in {"running", "queued"}),
            "knowledge_base_id": version["knowledge_base_id"], "version": version,
            "error": version.get("error") if status == "error" else None,
            "message": "服务重启后待处理导入可重新选择同一公告继续" if not job and status == "queued" else None}


@router.get("/{game_id}/templates")
async def game_templates(game_id: str) -> list[dict]:
    require_game(game_id)
    return templates_for(game_id)


@router.get("/{game_id}/sources")
async def game_sources(game_id: str) -> list[dict]:
    require_game(game_id)
    return sources_for(game_id)


@router.post("/{game_id}/knowledge-bases", status_code=201)
async def create_game_knowledge_base(game_id: str, body: dict = Body(...)) -> dict:
    game = require_game(game_id)
    try:
        profile = normalize_profile(body.get("profile") or {}, game_id=game_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return await call(store.create_knowledge_base, str(body.get("title") or game["title"]), str(body.get("description") or ""), game_profile=profile)


@router.get("/{game_id}/updates")
async def updates(game_id: str, source_id: str | None = None, limit: int = Query(default=10, ge=1, le=100)) -> dict:
    require_game(game_id)
    sources = sources_for(game_id)
    selected = [source for source in sources if source["id"] == source_id] if source_id else [source for source in sources if source["kind"] == "steam_news"]
    if not selected:
        raise HTTPException(status_code=422, detail="所选官方来源不属于此游戏")
    items, errors = [], []
    for source in selected:
        try:
            items.extend(await asyncio.to_thread(fetch_updates, game_id, source["id"], limit))
        except SourceError as error:
            errors.append({"source_id": source["id"], "url": source["url"], "error": str(error)})
    dedup = {item["url"]: item for item in items}
    visible = sorted(dedup.values(), key=lambda item: item.get("published_at") or "", reverse=True)[:limit]
    # Preview includes the source text; it does not silently import or claim latestness.
    return {"items": visible, "errors": errors, "latest_version_confirmed": False,
            "coverage": "bounded_official_sources", "captured_at": datetime.now(timezone.utc).isoformat()}


def _metadata(article: dict, *, edition: str | None = None, patch: str | None = None, mode: str | None = None,
              requires_dlc: list | None = None) -> dict:
    actual_edition = article.get("edition")
    if edition and actual_edition and edition != actual_edition:
        raise ValueError("所选发行版与官方来源的实际发行版不同")
    if patch and article.get("patch") and patch != article["patch"]:
        raise ValueError("所选补丁编号与公告明确编号不同")
    value = {"game_id": article["game_id"], "edition": actual_edition,
             "patch": article.get("patch"), "source_kind": article["source_kind"], "source_tier": article["source_tier"],
             "source_url": article["url"], "title": article["title"], "captured_at": article["captured_at"],
             "published_at": article.get("published_at"), "capture_sha256": article["content_sha256"],
             "content_sha256": article["content_sha256"], "provenance": article["provenance"],
             "requires_dlc": article.get("requires_dlc", [])}
    if article.get("mode"):
        value["mode"] = article["mode"]
    # Do not inherit a KB's current patch into an unversioned captured announcement.
    return normalize_metadata({key: value for key, value in value.items() if value is not None}, manual=False)


def _same_capture(version: dict, metadata: dict) -> bool:
    old = version.get("domain_metadata") or {}
    semantic = ("game_id", "edition", "patch", "source_url", "source_kind", "mode", "requires_dlc", "content_sha256", "title", "published_at")
    return all(old.get(key) == metadata.get(key) for key in semantic)


def _index_import(version: dict, path: Path, collection_name: str) -> None:
    identifier = version["id"]
    _IMPORTS[identifier] = {"status": "running"}
    metadata = version.get("domain_metadata") or {}
    source_metadata = {"knowledge_base_id": version["knowledge_base_id"], "document_series_id": version["document_series_id"],
                       "document_version_id": identifier, "version_label": version.get("version_label"),
                       "release_date": version.get("release_date"), "domain_metadata": metadata, **metadata}
    try:
        count = get_rag_service().index_document(path, collection_name, version["source_id"], version["filename"], source_metadata=source_metadata)
        store.update_document_version(identifier, "ready", chunk_count=count)
        _IMPORTS[identifier] = {"status": "completed"}
    except Exception:
        store.update_document_version(identifier, "error", error="公告索引未完成，请确认embedding配置后重新选择同一公告继续。")
        _IMPORTS[identifier] = {"status": "error"}


async def persist_capture(kb: dict, article: dict, background: BackgroundTasks, *, edition: str | None = None,
                          patch: str | None = None, mode: str | None = None, requires_dlc: list | None = None) -> dict:
    if article["game_id"] != kb.get("game_profile", {}).get("game_id"):
        raise ValueError("官方捕获所属游戏与知识库不同")
    metadata = _metadata(article, edition=edition, patch=patch, mode=mode, requires_dlc=requires_dlc)
    versions = await asyncio.to_thread(store.list_document_versions, kb["id"])
    existing = next((version for version in versions if _same_capture(version, metadata)), None)
    if existing:
        version = existing
        private = await asyncio.to_thread(store.resolve_document_version, version["id"])
        path = Path(private["file_path"])
    else:
        settings.ensure_storage_directories()
        slug = re.sub(r"[^A-Za-z0-9._-]", "-", article["source_id"])
        # Same source series permits comparisons of separate announcements, while
        # each immutable capture remains an independent document version.
        filename = f"{article['game_id']}-{slug}.md"
        path = settings.upload_dir / f"official_{uuid.uuid4().hex}.md"
        text = (f"# {article['title']}\n\nSource: {article['url']}\n"
                f"Published: {article.get('published_at') or 'unknown'}\nCaptured: {article['captured_at']}\n\n" + article["content"] + "\n")
        await asyncio.to_thread(path.write_text, text, encoding="utf-8")
        version = await asyncio.to_thread(store.create_document_version, kb["id"], filename, str(path), sha256(text.encode()).hexdigest(),
                                          article.get("patch") or "公告/资料快照", (article.get("published_at") or "")[:10] or None,
                                          {"game_id": article["game_id"], "edition": metadata.get("edition"), "patch": metadata.get("patch")}, domain_metadata=metadata)
    if version["status"] == "ready":
        return {"import_id": version["id"], "version_id": version["id"], "version": version, "status": "completed", "reused": True}
    if _IMPORTS.get(version["id"], {}).get("status") not in {"running", "queued"}:
        _IMPORTS[version["id"]] = {"status": "queued"}
        background.add_task(_index_import, version, path, kb["collection_name"])
    return {"import_id": version["id"], "version_id": version["id"], "version": version, "status": "queued", "reused": bool(existing)}


@router.post("/{game_id}/import", status_code=202)
async def import_article(game_id: str, background_tasks: BackgroundTasks, body: dict = Body(...)) -> dict:
    kb = await game_knowledge_base(game_id, str(body.get("knowledge_base_id", "")))
    source = next((source for source in sources_for(game_id) if source["id"] == body.get("source_id")), None)
    if source is None:
        raise HTTPException(status_code=422, detail="请选择本游戏的明确官方来源")
    try:
        if body.get("url"):
            article = await asyncio.to_thread(fetch_article, game_id, str(body["url"]), edition=source.get("edition"))
        elif body.get("external_id"):
            preview = await asyncio.to_thread(fetch_updates, game_id, source["id"], 100)
            article = next((item for item in preview if str(item["external_id"]) == str(body["external_id"])), None)
            if article is None:
                raise ValueError("所选公告不在该来源当前有界清单内，请刷新或使用实际公告链接")
        elif source["kind"] == "publisher_page":
            article = await asyncio.to_thread(fetch_article, game_id, source["url"], edition=source.get("edition"))
        else:
            raise ValueError("请从预览中明确选择公告，不自动导入所谓最新补丁")
        if article["source_id"] != source["id"]:
            raise ValueError("公告所属渠道与所选来源不同，请选择其实际渠道")
        return await persist_capture(kb, article, background_tasks, edition=body.get("edition"), patch=body.get("patch"),
                                     mode=body.get("mode"), requires_dlc=body.get("requires_dlc"))
    except SourceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{game_id}/tasks", status_code=201)
async def create_guide_task(game_id: str, body: dict = Body(...)) -> dict:
    kb = await game_knowledge_base(game_id, str(body.get("knowledge_base_id", "")))
    if body.get("conditions_confirmed") is not True:
        raise HTTPException(status_code=422, detail="请先确认游戏和攻略条件；未知条件可明确保留未知")
    profile = {**kb["game_profile"], **(body.get("profile") or {})}
    try:
        profile = normalize_profile(profile, game_id=game_id)
        payload = task_payload(profile, str(body.get("template_id", "")), str(body.get("goal", "")), body.get("player"))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    payload["context"]["conditions_confirmed"] = True
    return await call(store.create_research_task, kb["id"], payload["title"], payload["question"], payload["outline"], payload["context"])


@router.post("/{game_id}/impact")
async def game_patch_impact(game_id: str, body: dict = Body(...)) -> dict:
    kb = await game_knowledge_base(game_id, str(body.get("knowledge_base_id", "")))
    versions = await call(store.list_document_versions, kb["id"])
    if body.get("version_id"):
        versions = [version for version in versions if version["id"] == body["version_id"]]
        if not versions:
            raise HTTPException(status_code=404, detail="该补丁资料不属于当前知识库")
    tasks = await call(store.list_research_tasks, kb["id"])
    return await patch_impact(game_id, versions, tasks, get_rag_service(), query=str(body.get("query", "")))


def calculation_data(operation: str, data: dict) -> dict:
    value = deepcopy(data)
    if operation == "stat_budget":
        value.setdefault("current", value.get("starting_stats", {}))
        value.setdefault("target", value.get("target_stats", {}))
        if "budget" in value and "available_points" not in value:
            value["available_points"] = value["budget"]
    elif operation == "loadout_weight":
        value.setdefault("equipment", value.get("items", []))
    return value


@router.post("/{game_id}/calculate")
async def game_calculation(game_id: str, body: dict = Body(...)) -> dict:
    require_game(game_id)
    try:
        result = calculate(game_id, str(body.get("operation", "")), calculation_data(str(body.get("operation", "")), body.get("data") or {}), body.get("conditions"))
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    result.setdefault("warnings", []).append("玩家输入与所附来源标注不等于已核验原文；此结果只复算这些输入，不证明游戏机制或真实战斗伤害。")
    result["sources_verified"] = False
    result["sources"] = [{"source_id": item["source_id"], "quote": item["quote"], "provenance": "user_declared", "verified": False}
                         for item in result.get("inputs", []) if item.get("source_id") and item.get("quote")]
    return result
