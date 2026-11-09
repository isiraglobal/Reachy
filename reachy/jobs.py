"""Autonomous job execution, batch discovery, and CSV exporting for AI agents.

Built by ISIRA Automations for Reachy.
Ensures AI agents execute lead generation tasks end-to-end without modifying
codebase files, writing scratch scripts, or littering repository directories.
"""

from __future__ import annotations

import csv
import glob
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import ReachyConfig
from .db import Database
from .ingest import discover_leads, import_records
from .verify import DnspythonBackend, VerificationPolicy

logger = logging.getLogger(__name__)

CSV_LEAD_FIELDS = [
    "title",
    "name",
    "category",
    "phone",
    "email",
    "verification_status",
    "website",
    "address",
    "city",
    "state",
    "country",
    "rating",
    "reviews_count",
    "url",
    "source_url",
    "source_query",
    "tags",
    "qualification_score",
    "discovered_at",
]


def resolve_csv_output_path(
    list_name: Optional[str] = None,
    output_path: Optional[str | Path] = None,
    default_dir: str = "outputs",
) -> Path:
    """Resolves and ensures a destination CSV path in an output directory."""
    out_dir = Path(default_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = (list_name or "leads").strip().replace(" ", "_").lower()
    if not output_path or str(output_path).strip() == "" or str(output_path).strip() == "DEFAULT":
        return out_dir / f"{slug}.csv"

    dest = Path(output_path)
    if dest.is_dir() or str(output_path).endswith("/") or str(output_path).endswith("\\"):
        dest.mkdir(parents=True, exist_ok=True)
        return dest / f"{slug}.csv"

    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def export_leads_to_csv(
    records: list[dict[str, Any]],
    filepath: str | Path,
) -> Path:
    """Exports lead dictionaries directly to a standardized CSV file."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_LEAD_FIELDS, extrasaction="ignore")
        writer.writeheader()

        for raw_row in records:
            row = dict(raw_row)
            name_val = row.get("name") or row.get("title") or ""
            row["title"] = name_val
            row["name"] = name_val

            url_val = row.get("source_url") or row.get("url") or ""
            row["source_url"] = url_val
            row["url"] = url_val

            # Format tags if list or json
            tags_val = row.get("tags")
            if isinstance(tags_val, list):
                row["tags"] = ", ".join(str(t) for t in tags_val)

            # Ensure default empty string for missing fields
            for field in CSV_LEAD_FIELDS:
                if field not in row or row[field] is None:
                    row[field] = ""

            writer.writerow(row)

    logger.info("Exported %d leads to CSV: %s", len(records), path)
    return path


def export_list_to_csv(
    db: Database,
    list_name: Optional[str] = None,
    filepath: Optional[str | Path] = None,
    limit: int = 0,
    tags: Optional[list[str]] = None,
    task: Optional[str] = None,
    run: Optional[str] = None,
) -> tuple[Path, int]:
    """Queries leads from the database and exports them directly to CSV."""
    from .normalize import query_leads

    effective_limit = limit if limit > 0 else 100000

    if list_name or tags or task or run:
        records = query_leads(
            db,
            list_name=list_name,
            tags=tags,
            task=task,
            run=run,
            limit=effective_limit,
        )
    else:
        sql = """
            SELECT DISTINCT l.*, c.email, c.verification_status
            FROM leads l
            LEFT JOIN contacts c ON c.lead_id = l.id AND c.is_primary = 1
            ORDER BY l.id DESC
            LIMIT ?
        """
        rows = db.fetchall(sql, (effective_limit,))
        records = [dict(r) for r in rows]

    dest_path = resolve_csv_output_path(list_name=list_name, output_path=filepath)
    export_leads_to_csv(records, dest_path)
    return dest_path, len(records)


def run_discovery_job(
    db: Database,
    config: ReachyConfig,
    queries: list[str],
    list_name: str,
    limit_per_query: int = 20,
    csv_path: Optional[str | Path] = None,
    headed: bool = False,
    backend: str = "auto",
    enrich: bool = True,
    verify: bool = True,
    tags: Optional[list[str]] = None,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    clean_temp: bool = True,
) -> dict[str, Any]:
    """Executes an end-to-end multi-query discovery job, importing into SQLite and exporting CSV."""
    cleaned_queries = [q.strip() for q in queries if q and q.strip()]
    if not cleaned_queries:
        raise ValueError("At least one non-empty search query is required.")

    policy = VerificationPolicy(
        allow_catch_all=config.allow_catch_all,
        smtp_probe_enabled=config.catch_all_probe_enabled,
    )
    dns_backend = DnspythonBackend() if verify else None

    total_added = 0
    total_updated = 0
    total_skipped = 0
    query_reports = []

    try:
        for idx, q in enumerate(cleaned_queries, 1):
            logger.info("Job query [%d/%d]: '%s' (limit=%d)...", idx, len(cleaned_queries), q, limit_per_query)
            records = discover_leads(
                query=q,
                limit=limit_per_query,
                headed=headed,
                backend=backend,
                enrich=enrich,
            )

            stats = import_records(
                db,
                records,
                source="google_maps",
                list_name=list_name,
                source_query=q,
                verify=verify,
                dns_backend=dns_backend,
                verification_policy=policy,
                tags=tags or [],
                task=task_id,
                task_id=task_id,
                run=run_id,
                run_id=run_id,
            )

            added = stats.get("added", 0)
            updated = stats.get("updated", 0)
            skipped = stats.get("skipped", 0)
            total_added += added
            total_updated += updated
            total_skipped += skipped

            query_reports.append({
                "query": q,
                "scraped": len(records),
                "added": added,
                "updated": updated,
                "skipped": skipped,
            })
    finally:
        if clean_temp:
            clean_workspace(dry_run=False)

    dest_csv = resolve_csv_output_path(list_name=list_name, output_path=csv_path)
    final_path, total_in_csv = export_list_to_csv(
        db,
        list_name=list_name,
        filepath=dest_csv,
        tags=tags,
        task=task_id,
        run=run_id,
    )

    return {
        "ok": True,
        "list": list_name,
        "queries_count": len(cleaned_queries),
        "total_added": total_added,
        "total_updated": total_updated,
        "total_skipped": total_skipped,
        "total_in_csv": total_in_csv,
        "csv_path": str(final_path),
        "queries_detail": query_reports,
    }


def clean_workspace(
    repo_root: Optional[str | Path] = None,
    dry_run: bool = False,
) -> list[str]:
    """Sweeps stray scratch files, root JSON/CSV samples, and cache directories."""
    root = Path(repo_root or os.getcwd()).resolve()
    removed: list[str] = []

    # Patterns of files that should never sit in repo root
    stray_patterns = [
        "check_*.py",
        "export_*.py",
        "import_*.py",
        "batch_*.py",
        "*venues*.json",
        "*venues*.csv",
        "*sample*.json",
        "*sample*.csv",
        "*batch*.json",
        "additional_*.json",
        "marketpeace_*.json",
        "marketpeace_*.csv",
        "ny_venues_*.json",
        "pa_*.json",
        "pa_*.csv",
    ]

    for pattern in stray_patterns:
        for p in root.glob(pattern):
            if p.is_file():
                if not dry_run:
                    try:
                        p.unlink()
                    except OSError:
                        pass
                removed.append(str(p.relative_to(root)))

    # Empty folders to clean
    empty_folders = ["deploy", "data", "reachy/provider"]
    for folder in empty_folders:
        dir_path = root / folder
        if dir_path.is_dir() and not any(dir_path.iterdir()):
            if not dry_run:
                try:
                    dir_path.rmdir()
                except OSError:
                    pass
            removed.append(f"{folder}/")

    # Cache dirs
    cache_dirs = [".pytest_cache", "reachy.egg-info"]
    for c_dir in cache_dirs:
        dir_path = root / c_dir
        if dir_path.is_dir():
            if not dry_run:
                shutil.rmtree(dir_path, ignore_errors=True)
            removed.append(f"{c_dir}/")

    return removed

