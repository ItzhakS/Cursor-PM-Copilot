#!/usr/bin/env python3
"""
Fetch Notion pages and databases updated since the last incremental sync.

The script:
- Reads `lastIncrementalSyncTimestamp` from the Notion sync status doc.
- Queries databases and workspace pages touching only objects edited after that timestamp.
- Re-renders the affected markdown files (overwriting in place).
- Updates the status doc with a refreshed timestamp and a concise summary entry.
"""

from __future__ import annotations

import itertools
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from fetch_notion_docs import (  # type: ignore
    NOTION_API_SECRET,
    NOTION_DIR,
    STATUS_PATH,
    format_iso_timestamp,
    format_page_markdown,
    format_page_id_with_dashes,
    get_database_title,
    get_page_content,
    get_page_title,
    make_api_request,
    sanitize_filename,
)

# Script paths
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = NOTION_DIR.parents[2]

# Constants
TIMESTAMP_LABEL = "lastIncrementalSyncTimestamp"
PAGE_SIZE = 100
RATE_LIMIT_DELAY = 0.35  # seconds between paginated calls


class NotionIncrementalSyncError(Exception):
    """Raised when the incremental sync encounters a blocking error."""


def parse_iso_datetime(value: str) -> datetime:
    """Parse a Notion ISO timestamp into a timezone-aware datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_status_timestamp() -> Tuple[str, datetime]:
    """Read the status doc and extract the last incremental timestamp."""
    if not STATUS_PATH.exists():
        raise NotionIncrementalSyncError(f"Status doc not found at {STATUS_PATH}")
    
    text = STATUS_PATH.read_text(encoding="utf-8")
    pattern = rf"`{TIMESTAMP_LABEL}`:\s*([0-9T:\-]+Z)"
    match = re.search(pattern, text)
    if not match:
        raise NotionIncrementalSyncError(
            f"Could not locate `{TIMESTAMP_LABEL}` in status doc."
        )
    
    raw = match.group(1)
    return text, parse_iso_datetime(raw)


def discover_databases() -> List[Dict]:
    """Return all databases accessible to the integration (quiet discovery)."""
    results: List[Dict] = []
    has_more = True
    start_cursor: Optional[str] = None
    
    while has_more:
        payload = {
            "filter": {"value": "database", "property": "object"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": PAGE_SIZE,
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        response = make_api_request("POST", "search", payload)
        batch = response.get("results", [])
        results.extend(batch)
        
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
        time.sleep(RATE_LIMIT_DELAY)
    
    return results


def query_database_since(database_id: str, updated_after: datetime) -> List[Dict]:
    """Query a database for pages edited after the provided timestamp."""
    formatted_id = format_page_id_with_dashes(database_id.replace("-", ""))
    all_pages: List[Dict] = []
    has_more = True
    start_cursor: Optional[str] = None
    updated_after_iso = format_iso_timestamp(updated_after)
    
    while has_more:
        data: Dict = {
            "page_size": PAGE_SIZE,
            "filter": {
                "timestamp": "last_edited_time",
                "last_edited_time": {"after": updated_after_iso},
            },
        }
        if start_cursor:
            data["start_cursor"] = start_cursor
        
        response = make_api_request(
            "POST", f"databases/{formatted_id}/query", data
        )
        pages = response.get("results", [])
        all_pages.extend(pages)
        
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
        time.sleep(RATE_LIMIT_DELAY)
    
    return all_pages


def search_recent_pages(updated_after: datetime) -> List[Dict]:
    """Search workspace pages ordered by last edit and return only recent ones."""
    results: List[Dict] = []
    has_more = True
    start_cursor: Optional[str] = None
    
    while has_more:
        payload = {
            "filter": {"value": "page", "property": "object"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": PAGE_SIZE,
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        response = make_api_request("POST", "search", payload)
        batch = response.get("results", [])
        
        newer_items = []
        for page in batch:
            last_edited = page.get("last_edited_time")
            if not last_edited:
                continue
            last_dt = parse_iso_datetime(last_edited)
            if last_dt <= updated_after:
                continue
            newer_items.append(page)
        
        results.extend(newer_items)
        
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
        
        # If we didn't find any more recent pages in this batch, break early.
        if not newer_items:
            break
        
        time.sleep(RATE_LIMIT_DELAY)
    
    return results


def resolve_target_path(page: Dict, output_dir: Path) -> Path:
    """Determine the markdown path corresponding to a Notion page."""
    title = get_page_title(page)
    page_id = page.get("id", "")
    page_id_clean = page_id.replace("-", "")
    
    filename = sanitize_filename(title) + ".md"
    if not filename or filename == ".md":
        filename = f"page_{page_id_clean[:8]}.md"
    
    candidate = output_dir / filename
    if candidate.exists():
        return candidate
    
    # Attempt to locate by embedded page ID to handle duplicate titles
    for md_path in output_dir.glob("*.md"):
        try:
            if page_id_clean in md_path.read_text(encoding="utf-8"):
                return md_path
        except Exception:
            continue
    
    return candidate


def export_page(page: Dict, output_dir: Path) -> Optional[Path]:
    """Fetch page content and write markdown to disk."""
    page_id = page.get("id", "")
    if not page_id:
        return None
    
    formatted_id = format_page_id_with_dashes(page_id.replace("-", ""))
    page_url = page.get(
        "url", f"https://www.notion.so/{page_id.replace('-', '')}"
    )
    
    page_data, blocks = get_page_content(formatted_id)
    if not page_data:
        return None
    
    markdown = format_page_markdown(page_data, blocks, page_url)
    target_path = resolve_target_path(page, output_dir)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(markdown, encoding="utf-8")
    return target_path


def group_root_pages(pages: Iterable[Dict]) -> Dict[str, List[Dict]]:
    """Group pages by their top-level parent directory key."""
    grouped: Dict[str, List[Dict]] = {}
    for page in pages:
        parent = page.get("parent", {})
        parent_type = parent.get("type")
        if parent_type == "database_id":
            continue  # handled via database queries
        key = "Root Pages"
        grouped.setdefault(key, []).append(page)
    return grouped


def summarize_changes(updated: List[Path], new: List[Path]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    parts: List[str] = []
    if updated:
        parts.append(f"{len(updated)} updated")
    if new:
        parts.append(f"{len(new)} new")
    if not parts:
        parts.append("no changes")
    
    touched_paths = sorted(
        {str(path.relative_to(REPO_ROOT)) for path in itertools.chain(updated, new)}
    )
    files_part = ""
    if touched_paths:
        files_part = f" → touched {', '.join(touched_paths[:5])}"
        if len(touched_paths) > 5:
            files_part += ", …"
    
    return f"- {today}: {', '.join(parts)}{files_part}"


def update_status_doc(status_text: str, new_timestamp: datetime, summary_line: str) -> None:
    """Persist the new timestamp and summary into the status doc."""
    new_ts_str = format_iso_timestamp(new_timestamp)
    lines = status_text.splitlines()
    
    label_token = f"`{TIMESTAMP_LABEL}`"
    for idx, line in enumerate(lines):
        if label_token in line:
            lines[idx] = re.sub(
                rf"`{TIMESTAMP_LABEL}`:\s*[0-9T:\-]+Z",
                f"`{TIMESTAMP_LABEL}`: {new_ts_str}",
                line,
            )
            break
    else:
        raise NotionIncrementalSyncError(
            f"Failed to locate `{TIMESTAMP_LABEL}` in status doc."
        )
    
    try:
        section_idx = lines.index("## Incremental Summaries")
    except ValueError as exc:
        raise NotionIncrementalSyncError(
            "Could not locate '## Incremental Summaries' section."
        ) from exc
    
    insert_idx = section_idx + 1
    while insert_idx < len(lines) and lines[insert_idx].strip() == "":
        insert_idx += 1
    
    if insert_idx < len(lines) and lines[insert_idx].strip() == "_None yet_":
        lines[insert_idx] = summary_line
    elif insert_idx < len(lines) and lines[insert_idx].strip().startswith("- "):
        lines.insert(insert_idx, summary_line)
    else:
        lines.insert(insert_idx, summary_line)
    
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not NOTION_API_SECRET:
        raise NotionIncrementalSyncError("NOTION_API_SECRET is not configured.")
    
    status_text, last_sync_dt = load_status_timestamp()
    print(f"Last incremental sync: {format_iso_timestamp(last_sync_dt)}")
    
    databases = discover_databases()
    print(f"Discovered {len(databases)} database(s).")
    
    updated_paths: List[Path] = []
    new_paths: List[Path] = []
    latest_timestamp = last_sync_dt
    
    for database in databases:
        db_id = database.get("id")
        if not db_id:
            continue
        db_title = get_database_title(database)
        output_dir = NOTION_DIR / sanitize_filename(db_title)
        
        updated_pages = query_database_since(db_id, last_sync_dt)
        if not updated_pages:
            continue
        
        print(f"Processing {len(updated_pages)} updated page(s) in database '{db_title}'.")
        for page in updated_pages:
            target_path = resolve_target_path(page, output_dir)
            existed_before = target_path.exists()
            saved_path = export_page(page, output_dir)
            if not saved_path:
                continue
            
            page_last_edit = page.get("last_edited_time")
            if page_last_edit:
                page_dt = parse_iso_datetime(page_last_edit)
                if page_dt > latest_timestamp:
                    latest_timestamp = page_dt
            
            if existed_before:
                updated_paths.append(saved_path)
            else:
                new_paths.append(saved_path)
    
    recent_pages = search_recent_pages(last_sync_dt)
    root_groups = group_root_pages(recent_pages)
    for key, pages in root_groups.items():
        output_dir = NOTION_DIR / key
        if not pages:
            continue
        print(f"Processing {len(pages)} updated page(s) in '{key}'.")
        for page in pages:
            target_path = resolve_target_path(page, output_dir)
            existed_before = target_path.exists()
            saved_path = export_page(page, output_dir)
            if not saved_path:
                continue
            
            page_last_edit = page.get("last_edited_time")
            if page_last_edit:
                page_dt = parse_iso_datetime(page_last_edit)
                if page_dt > latest_timestamp:
                    latest_timestamp = page_dt
            
            if existed_before:
                updated_paths.append(saved_path)
            else:
                new_paths.append(saved_path)
    
    final_timestamp = max(latest_timestamp, datetime.now(timezone.utc))
    summary_line = summarize_changes(updated_paths, new_paths)
    update_status_doc(status_text, final_timestamp, summary_line)
    
    print(summary_line.replace("- ", "Summary: "))
    print(f"Status doc updated → {format_iso_timestamp(final_timestamp)}")


if __name__ == "__main__":
    try:
        main()
    except NotionIncrementalSyncError as exc:
        print(f"Incremental sync failed: {exc}")

