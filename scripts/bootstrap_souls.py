"""Preview/import the captured official Souls starter corpus; never claims latestness.

Default is a plan only. --apply creates/reuses dedicated game KBs and indexes
verified local capture contents. --knowledge-base-id requires one matching game.
No live network crawl or automatic report generation is performed.
"""
from __future__ import annotations

import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import BackgroundTasks
from config import settings
from souls_domain import catalog, task_payload
import workspace_store as store


def captures(game_ids: list[str]) -> dict[str, list[dict]]:
    result = {}
    for game_id in game_ids:
        path = ROOT / "knowledge" / "souls" / game_id / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        articles = manifest["articles"]
        for article in articles:
            if article["game_id"] != game_id or sha256(article["content"].encode()).hexdigest() != article["content_sha256"]:
                raise ValueError(f"Capture identity/hash mismatch: {path.name}")
        result[game_id] = articles
    return result


async def run(args: argparse.Namespace) -> None:
    games = catalog()
    game_ids = [game["id"] for game in games] if args.game == "all" else [args.game]
    if args.knowledge_base_id and len(game_ids) != 1:
        raise ValueError("--knowledge-base-id requires one specific --game")
    if args.goal and len(game_ids) != 1:
        raise ValueError("A draft goal requires one specific --game")
    plan = captures(game_ids)
    for game_id, articles in plan.items():
        print(f"{game_id}: {len(articles)} real captured sources")
        for article in articles:
            print(f"  {article['title']} | edition={article.get('edition')} | patch={article.get('patch')} | {article['url']}")
    if not args.apply:
        print("Plan only. Add --apply after schema/database/embedding configuration. Captures are not a latest-version guarantee.")
        return
    if not settings.database_url or not settings.embedding_model:
        raise ValueError("--apply requires DATABASE_URL and EMBEDDING_MODEL; apply scripts/init_db.sql first")
    # Keep the plan-only path independent of Ollama/vector clients entirely.
    from souls_api import persist_capture
    existing = await asyncio.to_thread(store.list_knowledge_bases)
    for game_id, articles in plan.items():
        game = next(game for game in games if game["id"] == game_id)
        title = f"[V3样板] {game['title']}"
        if args.knowledge_base_id:
            kb = await asyncio.to_thread(store.get_knowledge_base, args.knowledge_base_id)
            if not kb or kb.get("game_profile", {}).get("game_id") != game_id:
                raise ValueError("Selected knowledge base must already be bound to this game")
        else:
            kb = next((kb for kb in existing if kb["title"] == title and kb.get("game_profile", {}).get("game_id") == game_id), None)
            if kb is None:
                profile = {"game_id": game_id, "edition": articles[0].get("edition"), "spoiler_policy": "none"}
                kb = await asyncio.to_thread(store.create_knowledge_base, title, "真实官方资料样板；并非完整攻略或最新补丁保证。", profile)
                existing.append(kb)
        for article in articles:
            background = BackgroundTasks()
            imported = await persist_capture(kb, article, background)
            await background()
            version = await asyncio.to_thread(store.get_document_version, imported["version_id"])
            print(f"  {kb['id']} / {version['id']} -> {version['status']}")
            if version["status"] != "ready":
                raise RuntimeError(version.get("error") or "Source indexing did not complete")
        if args.goal:
            payload = task_payload(kb["game_profile"], args.template, args.goal)
            task = await asyncio.to_thread(store.create_research_task, kb["id"], payload["title"], payload["question"], payload["outline"], payload["context"])
            print(f"Draft task: {task['id']} (confirm outline in UI before running)")


if __name__ == "__main__":
    # Publisher titles include trademarks and non-ASCII names; redirected Windows
    # stdout otherwise defaults to GBK and may fail before showing the plan.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", choices=[game["id"] for game in catalog()] + ["all"], default="all")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--knowledge-base-id")
    parser.add_argument("--goal", help="Optional user-specified draft goal for a single game")
    parser.add_argument("--template", choices=["boss", "build", "route", "patch-impact", "guide-conflict"], default="patch-impact")
    try:
        asyncio.run(run(parser.parse_args()))
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
