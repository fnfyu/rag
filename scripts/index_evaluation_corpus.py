"""Index the checked-in evaluation corpus into a local Chroma collection.

This is intentionally separate from the web upload route: the benchmark corpus is
versioned, deterministic, and never depends on PostgreSQL conversation metadata.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import get_rag_service


DEFAULT_CORPUS = ROOT / "evaluation" / "corpus"
DEFAULT_COLLECTION = "eval_evidence_rag_v1"


def _snapshot_id(files: list[dict[str, object]], chunking: dict[str, object]) -> str:
    payload = {"files": files, "chunking": chunking}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"eval-{sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Index the Evidence RAG benchmark corpus")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--manifest", type=Path, default=ROOT / "evaluation" / "corpus-manifest.json")
    args = parser.parse_args()

    corpus = args.corpus.resolve()
    files = sorted(corpus.glob("*.md"))
    if not files:
        parser.error(f"no markdown corpus files found under {corpus}")

    service = get_rag_service()
    chunking: dict[str, object] = {
        "judgment_unit": "child",
        "parent_child_expansion": False,
        "parent_child_enabled": service.settings.parent_child_enabled,
        "parent_chunk_size": service.settings.parent_chunk_size,
        "parent_chunk_overlap": service.settings.parent_chunk_overlap,
        "child_chunk_size": service.settings.child_chunk_size,
        "child_chunk_overlap": service.settings.child_chunk_overlap,
        "expected_id_shape": "source_id:parent_index:child_index",
    }
    file_records = [
        {
            "filename": path.name,
            "source_id": f"eval:{path.name.casefold()}",
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
        for path in files
    ]
    snapshot_id = _snapshot_id(file_records, chunking)

    # Remove benchmark sources deleted from the checked-in corpus so a stale
    # local Chroma collection cannot quietly improve or corrupt the run.
    previous_manifest: dict[str, object] = {}
    if args.manifest.exists():
        try:
            previous_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous_manifest = {}
    current_sources = {str(record["source_id"]) for record in file_records}
    for old_record in previous_manifest.get("files", []) if isinstance(previous_manifest.get("files"), list) else []:
        if isinstance(old_record, dict) and old_record.get("source_id") not in current_sources:
            service._clear_indexed_source(args.collection, str(old_record["source_id"]))

    indexed: list[dict[str, object]] = []
    for path, record in zip(files, file_records):
        source_id = str(record["source_id"])
        chunk_count = service.index_document(path, args.collection, source_id, path.name)
        indexed.append(
            {
                **record,
                "chunk_count": chunk_count,
                "expected_first_chunk_id": f"{source_id}:0:0",
            }
        )

    manifest = {
        "snapshot_id": snapshot_id,
        "collection_name": args.collection,
        "corpus": str(corpus.relative_to(ROOT)) if corpus.is_relative_to(ROOT) else "local benchmark corpus",
        "files": indexed,
        "chunking": chunking,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.manifest.with_name(f".{args.manifest.name}.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
