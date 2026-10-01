"""Version comparison, real page geometry, image questions and table calculations."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException
from starlette.responses import FileResponse

from backend import get_rag_service
from config import settings
from evidence import metadata_value
from multimodal import IMAGE_EXTENSIONS, describe_image, extract_pdf
from report_api import call
from security import require_api_key
from table_analysis import TableAnalysisError, calculate_table, parse_tables
from version_analysis import compare_versions, version_text
import workspace_store as store

router = APIRouter(prefix="/documents", tags=["document-research"], dependencies=[Depends(require_api_key)])
_PAGE_CACHE: dict[str, list[dict]] = {}


async def require_version(version_id: str, *, private: bool = False) -> dict:
    version = await call(store.resolve_document_version if private else store.get_document_version, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="资料版本不存在")
    return version


def _pages(version: dict) -> list[dict]:
    if version["id"] in _PAGE_CACHE:
        return deepcopy(_PAGE_CACHE[version["id"]])
    service = get_rag_service()
    path = Path(version["file_path"])
    source_id = version["source_id"]
    if path.suffix.lower() == ".pdf":
        if not path.exists():
            raise ValueError("原始PDF文件不存在，无法定位页面区域")
        documents = extract_pdf(path, settings.asset_dir, source_id, render_enabled=settings.pdf_page_render_enabled)
        grouped: dict[int, dict] = {}
        seen_tables: set[str] = set()
        for document in documents:
            metadata = document.metadata
            page_number = int(metadata["page_number"])
            asset_key = metadata.get("asset_key")
            page = grouped.setdefault(page_number, {"page_number": page_number, "width": metadata["page_width"], "height": metadata["page_height"],
                "asset_key": asset_key, "asset_url": "/documents/assets/" + quote(asset_key, safe="/") if asset_key else None,
                "coordinate_system": "unrotated_mupdf_points", "regions": [], "tables": []})
            page["regions"].append({"bbox": metadata_value(metadata.get("bbox"), []), "content": document.page_content,
                                    "region_type": metadata.get("region_type", "text"), "evidence_modality": metadata.get("evidence_modality", "text"),
                                    "is_literal": metadata.get("is_literal", True), "source_id": source_id})
            if metadata.get("table_json"):
                for table in parse_tables(metadata["table_json"], source_id, version["filename"]):
                    if table["id"] not in seen_tables:
                        page["tables"].append(table)
                        seen_tables.add(table["id"])
        pages = list(grouped.values())
    elif path.suffix.lower() in IMAGE_EXTENSIONS:
        from PIL import Image
        key = sha256(source_id.encode()).hexdigest()
        target = settings.asset_dir / key / "image.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as image:
            width, height = image.size
            image.convert("RGB").save(target)
        pages = [{"page_number": 1, "width": width, "height": height, "asset_key": f"{key}/image.png",
                  "asset_url": f"/documents/assets/{key}/image.png", "coordinate_system": "image_pixels",
                  "regions": [{"bbox": [0, 0, width, height], "content": "", "region_type": "image", "evidence_modality": "image", "is_literal": False}], "tables": []}]
    else:
        text = version_text(version, service)
        tables = parse_tables(text, source_id, version["filename"])
        pages = [{"page_number": 1, "is_virtual_page": True, "label": "文本资料（无分页）", "width": 0, "height": 0,
                  "asset_url": None, "regions": [{"bbox": [], "content": text, "region_type": "text", "evidence_modality": "text", "is_literal": True}],
                  "tables": tables}]
    _PAGE_CACHE[version["id"]] = deepcopy(pages)
    return pages


@router.get("/series/{series_id}/compare")
async def compare_document_versions(series_id: str, left_version: str, right_version: str, applicability: str = "") -> dict:
    left, right = await require_version(left_version), await require_version(right_version)
    if left["document_series_id"] != series_id or right["document_series_id"] != series_id:
        raise HTTPException(status_code=422, detail="请选择同一资料系列中的两个版本")
    return await compare_versions(left, right, get_rag_service(), applicability=applicability)


@router.get("/versions/{version_id}/pages")
async def document_pages(version_id: str) -> list[dict]:
    version = await require_version(version_id, private=True)
    try:
        pages = await asyncio.to_thread(_pages, version)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    # Filesystem asset keys are relative hashes; original upload paths never leave the module.
    return [{**page, "document_version_id": version["id"], "filename": version["filename"]} for page in pages]


@router.post("/versions/{version_id}/pages/{page_number}/analyze")
async def analyze_page(version_id: str, page_number: int, body: dict = Body(...)) -> dict:
    question = str(body.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=422, detail="请填写针对本页图像的问题")
    version = await require_version(version_id, private=True)
    pages = await asyncio.to_thread(_pages, version)
    page = next((item for item in pages if item["page_number"] == page_number), None)
    if page is None or not page.get("asset_key"):
        raise HTTPException(status_code=422, detail="该资料没有可分析的实际页面图像")
    path = settings.asset_dir / page["asset_key"]
    if not path.exists():
        raise HTTPException(status_code=422, detail="页面预览未生成，请启用PDF页面渲染")
    bbox = body.get("bbox") or [0, 0, page["width"], page["height"]]
    if len(bbox) != 4 or not (0 <= bbox[0] < bbox[2] <= page["width"] and 0 <= bbox[1] < bbox[3] <= page["height"]):
        raise HTTPException(status_code=422, detail="分析区域超出实际页面范围")
    if bbox != [0, 0, page["width"], page["height"]]:
        from PIL import Image
        with Image.open(path) as image:
            coordinates = (round(bbox[0] / page["width"] * image.width), round(bbox[1] / page["height"] * image.height),
                           round(bbox[2] / page["width"] * image.width), round(bbox[3] / page["height"] * image.height))
            cropped = image.crop(coordinates)
            key = sha256(json.dumps(bbox).encode()).hexdigest()[:16]
            path = path.with_name(f"region-{key}.png")
            cropped.save(path)
    service = get_rag_service()
    try:
        async with asyncio.timeout(settings.vision_timeout_seconds):
            answer = await asyncio.to_thread(describe_image, path, question, service.vision_llm, settings.vision_timeout_seconds)
    except Exception as error:
        raise HTTPException(status_code=503, detail="图像分析未完成，请配置并启动实际支持视觉输入的 VISION_MODEL。") from error
    return {"answer": answer, "page_number": page_number, "bbox": bbox, "document_version_id": version["id"],
            "source_id": version["source_id"], "evidence_modality": "visual_description", "is_literal": False,
            "asset_url": page["asset_url"], "disclaimer": "这是实际图像的模型解读，不是页面原始文字或真实性证明。"}


@router.post("/versions/{version_id}/tables/calculate")
async def calculate_document_table(version_id: str, body: dict = Body(...)) -> dict:
    version = await require_version(version_id, private=True)
    pages = await asyncio.to_thread(_pages, version)
    table = next((table for page in pages for table in page["tables"] if table["id"] == body.get("table_id")), None)
    if table is None:
        raise HTTPException(status_code=404, detail="指定表格不存在，请先加载该版本的表格")
    table = deepcopy(table)
    if "row_a" in body or "row_b" in body:
        a, b = body.get("row_a"), body.get("row_b")
        if type(a) is not int or type(b) is not int or a == b or not (0 <= a < len(table["rows"]) and 0 <= b < len(table["rows"])):
            raise HTTPException(status_code=422, detail="请选择两个不同的有效0基来源行索引")
        table["rows"] = [table["rows"][a], table["rows"][b]]
        table["row_numbers"] = [table["row_numbers"][a], table["row_numbers"][b]]
    try:
        result = calculate_table(table, body.get("operation", ""), body.get("column"), body.get("filters"), body.get("group_by"))
    except TableAnalysisError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {**result, "table_id": table["id"], "document_version_id": version["id"],
            "selected_indices": [body["row_a"], body["row_b"]] if "row_a" in body else None}


@router.get("/assets/{asset_key:path}")
async def page_asset(asset_key: str) -> FileResponse:
    root = settings.asset_dir.resolve()
    path = (root / asset_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="页面图像不存在")
    return FileResponse(path, media_type="image/png")
