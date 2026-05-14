#!/usr/bin/env python3
# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database.knowledgebase_operations import (  # noqa: E402
    ensure_repository_schema,
    list_repositories,
    update_repository,
)
from service.core.file_parse import execute_insert_process  # noqa: E402
from service.core.rag.app.code_repo import supports_path as code_repo_supports_path  # noqa: E402
from service.core.rag.utils.es_conn import ESConnection  # noqa: E402
from utils.database import SessionLocal  # noqa: E402


@dataclass
class RepositoryTarget:
    id: str
    name: str
    user_id: str
    index_name: str
    source_path: str
    root_path: str | None
    metadata: dict[str, Any]
    raw: dict[str, Any]


@dataclass
class RepositoryHealth:
    repository_id: str
    name: str
    status: str | None
    source_path: str
    source_exists: bool
    parser_supported: bool
    db_indexed_chunks: int | None
    es_docs: int
    drift: int | None
    recommendation: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def repository_target_from_row(row: dict[str, Any]) -> RepositoryTarget:
    metadata = parse_json(row.get("metadata_json"))
    source_path = (
        metadata.get("source_path")
        or row.get("root_path")
        or row.get("storage_path")
        or ""
    )
    return RepositoryTarget(
        id=row["id"],
        name=row["name"],
        user_id=row["user_id"],
        index_name=row.get("index_name") or row["user_id"],
        source_path=source_path,
        root_path=row.get("root_path"),
        metadata=metadata,
        raw=row,
    )


def inspect_repository_health(
    es_conn: ESConnection,
    target: RepositoryTarget,
) -> RepositoryHealth:
    source_exists = bool(target.source_path) and Path(target.source_path).exists()
    parser_supported = source_exists and code_repo_supports_path(target.source_path)
    es_docs = count_query(
        es_conn,
        target.index_name,
        {"term": {"repository_id": target.id}},
    )
    db_indexed_chunks = target.raw.get("indexed_chunks")
    drift = None
    if isinstance(db_indexed_chunks, int):
        drift = es_docs - db_indexed_chunks

    if not source_exists:
        recommendation = "source_missing_reupload_or_fix_path"
    elif not parser_supported:
        recommendation = "source_not_supported_check_root_path"
    elif es_docs == 0:
        recommendation = "rebuild_required_empty_index"
    elif drift not in (None, 0):
        recommendation = "rebuild_recommended_chunk_drift"
    elif target.raw.get("status") == "error":
        recommendation = "rebuild_required_status_error"
    else:
        recommendation = "healthy"

    return RepositoryHealth(
        repository_id=target.id,
        name=target.name,
        status=target.raw.get("status"),
        source_path=target.source_path,
        source_exists=source_exists,
        parser_supported=parser_supported,
        db_indexed_chunks=db_indexed_chunks,
        es_docs=es_docs,
        drift=drift,
        recommendation=recommendation,
    )


def resolve_targets(
    user_id: str,
    repository_id: str | None = None,
    repository_name: str | None = None,
    include_all: bool = False,
) -> list[RepositoryTarget]:
    with SessionLocal() as db:
        ensure_repository_schema(db)
        repositories = list_repositories(user_id, db=db)

    if not repositories:
        return []

    if include_all:
        return [repository_target_from_row(row) for row in repositories]

    if repository_id:
        for row in repositories:
            if row["id"] == repository_id:
                return [repository_target_from_row(row)]
        return []

    if repository_name:
        matched = [row for row in repositories if row["name"] == repository_name]
        return [repository_target_from_row(row) for row in matched]

    raise ValueError("Specify --all, --repository-id, or --repository-name")


def count_query(es_conn: ESConnection, index_name: str, query: dict[str, Any]) -> int:
    if not es_conn.es.indices.exists(index=index_name):
        return 0
    response = es_conn.es.count(index=index_name, body={"query": query})
    return int(response.get("count", 0))


def safe_count_query(es_conn: ESConnection, index_name: str, query: dict[str, Any], label: str) -> int | None:
    try:
        return count_query(es_conn, index_name, query)
    except Exception as exc:
        print(f"[audit] skip_count[{label}]={exc}")
        return None


def search_samples(
    es_conn: ESConnection,
    index_name: str,
    query: dict[str, Any],
    size: int = 5,
) -> list[dict[str, Any]]:
    if not es_conn.es.indices.exists(index=index_name):
        return []
    response = es_conn.es.search(
        index=index_name,
        body={
            "size": size,
            "_source": [
                "repository_id",
                "kb_id",
                "user_id",
                "docnm_kwd",
                "file_path_kwd",
                "symbol_kwd",
                "language_kwd",
            ],
            "query": query,
        },
    )
    return [hit.get("_source", {}) for hit in response.get("hits", {}).get("hits", [])]


def collect_orphan_repository_ids(
    es_conn: ESConnection,
    index_name: str,
    valid_repository_ids: set[str],
) -> dict[str, int]:
    if not es_conn.es.indices.exists(index=index_name):
        return {}

    response = es_conn.es.search(
        index=index_name,
        body={
            "size": 0,
            "aggs": {
                "repository_ids": {
                    "terms": {
                        "field": "repository_id.keyword",
                        "size": 10000,
                        "missing": "__missing__",
                    }
                }
            },
        },
    )
    buckets = response.get("aggregations", {}).get("repository_ids", {}).get("buckets", [])
    orphans: dict[str, int] = {}
    for bucket in buckets:
        key = str(bucket.get("key"))
        if key == "__missing__":
            continue
        if key not in valid_repository_ids:
            orphans[key] = int(bucket.get("doc_count", 0))
    return orphans


def build_dirty_queries(user_id: str, orphan_repository_ids: list[str]) -> dict[str, dict[str, Any]]:
    queries: dict[str, dict[str, Any]] = {
        "missing_repository_id": {"bool": {"must_not": {"exists": {"field": "repository_id"}}}},
        "missing_kb_id": {"bool": {"must_not": {"exists": {"field": "kb_id"}}}},
        "wrong_user_id": {
            "bool": {
                "must_not": {"term": {"user_id": user_id}},
            }
        },
        "kb_repository_mismatch": {
            "script": {
                "script": {
                    "lang": "painless",
                    "source": """
                        if (!doc.containsKey('repository_id') || doc['repository_id'].size() == 0) return false;
                        if (!doc.containsKey('kb_id') || doc['kb_id'].size() == 0) return false;
                        return String.valueOf(doc['repository_id'].value) != String.valueOf(doc['kb_id'].value);
                    """,
                }
            }
        },
    }
    if orphan_repository_ids:
        queries["orphan_repository_id"] = {"terms": {"repository_id.keyword": orphan_repository_ids}}
    return queries


def audit_user_index(user_id: str, sample_size: int) -> int:
    es_conn = ESConnection()
    index_name = user_id

    with SessionLocal() as db:
        ensure_repository_schema(db)
        repositories = list_repositories(user_id, db=db)

    valid_repository_ids = {row["id"] for row in repositories}
    targets = [repository_target_from_row(row) for row in repositories]
    print(f"[audit] user_id={user_id} index={index_name}")
    print(f"[audit] repositories_in_db={len(repositories)}")

    if not es_conn.es.indices.exists(index=index_name):
        print("[audit] index does not exist")
        return 0

    total_docs = count_query(es_conn, index_name, {"match_all": {}})
    orphans = collect_orphan_repository_ids(es_conn, index_name, valid_repository_ids)
    dirty_queries = build_dirty_queries(user_id, list(orphans.keys()))

    print(f"[audit] total_docs={total_docs}")
    print(f"[audit] orphan_repository_ids={orphans}")

    dirty_counts: dict[str, int | None] = {}
    for label, query in dirty_queries.items():
        dirty_counts[label] = safe_count_query(es_conn, index_name, query, label)

    for label, count in dirty_counts.items():
        print(f"[audit] {label}={count}")
        if count and sample_size > 0:
            try:
                samples = search_samples(es_conn, index_name, dirty_queries[label], size=sample_size)
                print(f"[audit] samples[{label}]={json.dumps(samples, ensure_ascii=False, indent=2)}")
            except Exception as exc:
                print(f"[audit] skip_samples[{label}]={exc}")

    repository_health = [
        inspect_repository_health(es_conn, target).__dict__ for target in targets
    ]
    print("[audit] repository_health=")
    print(json.dumps(repository_health, ensure_ascii=False, indent=2))
    return 0


def cleanup_dirty_docs(user_id: str, apply: bool) -> int:
    es_conn = ESConnection()
    index_name = user_id

    with SessionLocal() as db:
        ensure_repository_schema(db)
        repositories = list_repositories(user_id, db=db)

    valid_repository_ids = {row["id"] for row in repositories}
    orphan_repository_ids = list(collect_orphan_repository_ids(es_conn, index_name, valid_repository_ids).keys())
    dirty_queries = build_dirty_queries(user_id, orphan_repository_ids)
    should_clauses = [dirty_queries[key] for key in dirty_queries]
    delete_query = {"query": {"bool": {"should": should_clauses, "minimum_should_match": 1}}}
    preview_count = count_query(es_conn, index_name, delete_query["query"])

    print(f"[cleanup] user_id={user_id} index={index_name}")
    print(f"[cleanup] delete_candidates={preview_count}")
    print(f"[cleanup] orphan_repository_ids={orphan_repository_ids}")
    for label, query in dirty_queries.items():
        count = safe_count_query(es_conn, index_name, query, label)
        print(f"[cleanup] {label}={count}")
    if not apply:
        print("[cleanup] dry-run only. Re-run with --apply to delete dirty documents.")
        return 0

    if not es_conn.es.indices.exists(index=index_name):
        print("[cleanup] index does not exist")
        return 0

    response = es_conn.es.delete_by_query(
        index=index_name,
        body=delete_query,
        conflicts="proceed",
        refresh=True,
    )
    print(f"[cleanup] deleted={response.get('deleted', 0)}")
    return 0


def rebuild_repositories(
    user_id: str,
    targets: list[RepositoryTarget],
    apply: bool,
    clean_dirty_first: bool,
) -> int:
    if not targets:
        print("[rebuild] no repositories matched the selection")
        return 1

    if clean_dirty_first:
        cleanup_dirty_docs(user_id, apply=apply)

    es_conn = ESConnection()
    failed = False
    with SessionLocal() as db:
        ensure_repository_schema(db)
        for target in targets:
            source_path = Path(target.source_path)
            if not source_path.exists():
                print(f"[rebuild] skip {target.name}: source_path missing -> {source_path}")
                update_repository(
                    target.id,
                    user_id,
                    status="error",
                    metadata={
                        **target.metadata,
                        "last_rebuild_error": f"Missing source path: {source_path}",
                        "last_rebuild_at": utc_now_iso(),
                    },
                    db=db,
                )
                db.commit()
                continue

            current_count = count_query(
                es_conn,
                target.index_name,
                {"term": {"repository_id": target.id}},
            )
            health = inspect_repository_health(es_conn, target)
            print(
                f"[rebuild] repository={target.name} id={target.id} "
                f"source={source_path} current_docs={current_count} "
                f"recommendation={health.recommendation}"
            )

            if not apply:
                continue

            try:
                es_conn.delete_by_metadata(target.index_name, {"repository_id": target.id})
                update_repository(target.id, user_id, status="indexing", db=db)
                db.commit()

                indexing = execute_insert_process(
                    str(source_path),
                    target.name,
                    repository_id=target.id,
                    user_id=user_id,
                    index_name=target.index_name,
                )

                metadata = dict(target.metadata)
                metadata.update(
                    {
                        "source_path": str(source_path),
                        "root_path": target.raw.get("root_path") or str(source_path),
                        "doc_ids": indexing.doc_ids,
                        "last_rebuild_at": utc_now_iso(),
                        "last_rebuild_error": "",
                        "index_strategy": "shared_user_index+repository_filter",
                        "chunk_metadata_fields": [
                            "repository_id",
                            "kb_id",
                            "user_id",
                            "doc_id",
                            "file_path_kwd",
                            "symbol_kwd",
                            "language_kwd",
                            "chunk_kind_kwd",
                        ],
                    }
                )
                update_repository(
                    target.id,
                    user_id,
                    status="ready",
                    file_count=indexing.file_count,
                    indexed_chunks=indexing.indexed_chunks,
                    language_stats=indexing.language_stats,
                    metadata=metadata,
                    db=db,
                )
                db.commit()
                print(
                    f"[rebuild] rebuilt {target.name}: indexed_chunks={indexing.indexed_chunks} "
                    f"file_count={indexing.file_count}"
                )
            except Exception as exc:
                failed = True
                db.rollback()
                update_repository(
                    target.id,
                    user_id,
                    status="error",
                    metadata={
                        **target.metadata,
                        "last_rebuild_error": str(exc),
                        "last_rebuild_at": utc_now_iso(),
                    },
                    db=db,
                )
                db.commit()
                print(f"[rebuild] failed {target.name}: {exc}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit, clean, and rebuild ES repository indexes for code knowledge bases.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Inspect ES metadata quality and repository counts.")
    audit.add_argument("--user-id", required=True)
    audit.add_argument("--sample-size", type=int, default=3)

    cleanup = subparsers.add_parser("cleanup", help="Delete dirty legacy/orphan ES documents.")
    cleanup.add_argument("--user-id", required=True)
    cleanup.add_argument("--apply", action="store_true")

    rebuild = subparsers.add_parser("rebuild", help="Rebuild repository chunks into ES.")
    rebuild.add_argument("--user-id", required=True)
    rebuild.add_argument("--repository-id")
    rebuild.add_argument("--repository-name")
    rebuild.add_argument("--all", action="store_true")
    rebuild.add_argument("--apply", action="store_true")
    rebuild.add_argument("--clean-dirty-first", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "audit":
        return audit_user_index(args.user_id, sample_size=args.sample_size)

    if args.command == "cleanup":
        return cleanup_dirty_docs(args.user_id, apply=args.apply)

    if args.command == "rebuild":
        targets = resolve_targets(
            user_id=args.user_id,
            repository_id=args.repository_id,
            repository_name=args.repository_name,
            include_all=args.all,
        )
        return rebuild_repositories(
            user_id=args.user_id,
            targets=targets,
            apply=args.apply,
            clean_dirty_first=args.clean_dirty_first,
        )

    parser.error("Unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
