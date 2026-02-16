#!/usr/bin/env python3
"""
Fetch Linear issues updated since the last sync and refresh the affected batch files.
Also updates the Linear sync status doc with the new timestamp and a brief summary.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

# Repository paths: set LINEAR_OUTPUT_DIR to override where batch markdown and status are written
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent.parent
LINEAR_DIR = Path(os.environ.get("LINEAR_OUTPUT_DIR", REPO_ROOT / "output" / "Linear"))
STATUS_PATH = LINEAR_DIR / "Linear-Sync-Status.md"

LINEAR_DIR.mkdir(parents=True, exist_ok=True)

# Linear API configuration: set LINEAR_API_KEY and optionally LINEAR_TEAM_NAME in environment
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TEAM_NAME = os.environ.get("LINEAR_TEAM_NAME", "My Team")
LINEAR_BATCH_PREFIX = os.environ.get("LINEAR_BATCH_PREFIX", "Issues-Batch")
BATCH_SIZE = 50

HEADERS = {
    "Authorization": LINEAR_API_KEY,
    "Content-Type": "application/json",
}


class LinearSyncError(Exception):
    """Raised when the sync process encounters an unrecoverable error."""


@dataclass
class IssueEntry:
    identifier: str
    content: str

    @property
    def numeric_id(self) -> int:
        return get_numeric_identifier(self.identifier)


def make_graphql_request(query: str, variables: Optional[dict] = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    response = requests.post(LINEAR_API_URL, headers=HEADERS, json=payload)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = ""
        try:
            detail = f" Response: {response.text}"
        except Exception:  # noqa: BLE001
            detail = ""
        raise LinearSyncError(f"HTTP {response.status_code} {exc}{detail}") from exc

    data = response.json()
    if "errors" in data:
        raise LinearSyncError(data["errors"])
    return data


def get_team_id(team_name: Optional[str] = None) -> str:
    team_name = team_name or LINEAR_TEAM_NAME
    query = """
    query GetTeams {
        teams {
            nodes {
                id
                name
            }
        }
    }
    """
    result = make_graphql_request(query)
    teams = result["data"]["teams"]["nodes"]
    for team in teams:
        if team["name"] == team_name:
            return team["id"]
    raise LinearSyncError(f"Could not find team named '{team_name}'")


def fetch_comments(issue_id: str) -> List[dict]:
    query = """
    query GetComments($issueId: String!) {
        issue(id: $issueId) {
            comments {
                nodes {
                    body
                    createdAt
                    user {
                        name
                    }
                }
            }
        }
    }
    """
    try:
        result = make_graphql_request(query, {"issueId": issue_id})
        issue = result.get("data", {}).get("issue")
        if issue and issue.get("comments"):
            return issue["comments"]["nodes"]
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: failed to fetch comments for {issue_id}: {exc}")
    return []


def format_issue(issue: dict, comments: Iterable[dict]) -> str:
    lines: List[str] = []
    lines.append(f"# {issue['identifier']}: {issue['title']}\n")

    metadata: List[str] = []
    if issue.get("state"):
        metadata.append(f"**Status:** {issue['state']['name']}")
    if issue.get("labels") and issue["labels"].get("nodes"):
        label_names = [label["name"] for label in issue["labels"]["nodes"]]
        if label_names:
            metadata.append(f"**Labels:** {', '.join(label_names)}")
    if issue.get("priority") is not None:
        metadata.append(f"**Priority:** {issue['priority']}")
    if issue.get("assignee"):
        metadata.append(f"**Assignee:** {issue['assignee']['name']}")
    if issue.get("creator"):
        metadata.append(f"**Created By:** {issue['creator']['name']}")
    if issue.get("createdAt"):
        metadata.append(f"**Created:** {issue['createdAt'].split('T')[0]}")
    if issue.get("updatedAt"):
        metadata.append(f"**Updated:** {issue['updatedAt'].split('T')[0]}")
    if issue.get("dueDate"):
        metadata.append(f"**Due Date:** {issue['dueDate'].split('T')[0]}")
    if issue.get("team"):
        metadata.append(f"**Team:** {issue['team']['name']}")
    if issue.get("cycle"):
        metadata.append(f"**Cycle:** {issue['cycle']['name']}")
    if issue.get("project"):
        metadata.append(f"**Project:** {issue['project']['name']}")
    if issue.get("url"):
        metadata.append(f"**Linear URL:** {issue['url']}")
    if issue.get("branchName"):
        metadata.append(f"**Git Branch:** {issue['branchName']}")

    if metadata:
        lines.append(" ".join(metadata) + "\n")

    lines.append("\n## Description\n\n")
    if issue.get("description"):
        lines.append(issue["description"] + "\n")
    else:
        lines.append("_No description provided._\n")

    lines.append("\n## Comments\n\n")
    if comments:
        for comment in comments:
            author_name = comment.get("user", {}).get("name") or "Unknown"
            created_at = (
                comment.get("createdAt", "").split("T")[0] if comment.get("createdAt") else ""
            )
            body = comment.get("body") or ""
            lines.append(f"### {author_name} - {created_at}\n\n")
            lines.append(f"{body}\n\n")
    else:
        lines.append("_No comments yet._\n")

    lines.append("\n---\n\n")
    return "".join(lines)


def get_numeric_identifier(identifier: str) -> int:
    if not identifier:
        return int(1e12)
    parts = re.split(r"[-_]", identifier)
    for part in reversed(parts):
        match = re.search(r"\d+", part)
        if match:
            return int(match.group())
    return int(1e12)


def parse_status_doc(timestamp_label: str = "lastSyncTimestamp") -> Tuple[str, datetime]:
    if not STATUS_PATH.exists():
        raise LinearSyncError(f"Status doc not found at {STATUS_PATH}")
    text = STATUS_PATH.read_text(encoding="utf-8")
    pattern = rf"`{timestamp_label}`:\s*([0-9T:\-]+Z)"
    match = re.search(pattern, text)
    if not match:
        raise LinearSyncError(f"Could not locate `{timestamp_label}` in status doc.")

    raw_timestamp = match.group(1)
    parsed = parse_iso_datetime(raw_timestamp)
    return text, parsed


def parse_iso_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def fetch_updated_issues(team_id: str, updated_after: datetime) -> List[dict]:
    query = """
    query IssuesUpdatedSince($teamId: ID!, $updatedAfter: DateTimeOrDuration!, $after: String) {
        issues(
            filter: {
                team: { id: { eq: $teamId } }
                updatedAt: { gt: $updatedAfter }
            }
            orderBy: updatedAt
            first: 100
            after: $after
        ) {
            pageInfo {
                hasNextPage
                endCursor
            }
            nodes {
                id
                identifier
                title
                description
                url
                state { name }
                priority
                assignee { name }
                creator { name }
                createdAt
                updatedAt
                dueDate
                team { name }
                cycle { name }
                project { name }
                branchName
                labels { nodes { name } }
            }
        }
    }
    """

    variables = {
        "teamId": team_id,
        "updatedAfter": format_iso_timestamp(updated_after),
        "after": None,
    }

    issues: List[dict] = []
    while True:
        result = make_graphql_request(query, variables)
        data = result["data"]["issues"]
        issues.extend(data["nodes"])
        if not data["pageInfo"]["hasNextPage"]:
            break
        variables["after"] = data["pageInfo"]["endCursor"]
    return issues


def load_existing_entries() -> Tuple[List[IssueEntry], Dict[int, Dict[str, object]]]:
    entries: List[IssueEntry] = []
    batches: Dict[int, Dict[str, object]] = {}

    batch_files = sorted(
        LINEAR_DIR.glob(f"{LINEAR_BATCH_PREFIX}-*.md"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)),
    )

    for path in batch_files:
        match = re.search(r"(\d+)", path.stem)
        if not match:
            continue
        batch_num = int(match.group(1))
        text = path.read_text(encoding="utf-8")
        try:
            header, remainder = text.split("\n---\n\n", 1)
        except ValueError:
            raise LinearSyncError(f"Unexpected format in {path}")

        blocks = remainder.split("\n---\n\n")
        identifiers: List[str] = []

        for block in blocks:
            stripped = block.strip()
            if not stripped:
                continue
            lines = stripped.splitlines()
            first_line = lines[0].strip()
            if not first_line.startswith("# "):
                continue
            identifier = first_line[2:].split(":", 1)[0].strip()
            identifiers.append(identifier)
            content = stripped + "\n---\n\n"
            entry = IssueEntry(identifier=identifier, content=content)
            entries.append(entry)

        batches[batch_num] = {
            "path": path,
            "header": header,
            "identifiers": identifiers,
            "raw_content": text,
        }

    return entries, batches


def insert_new_entry(entries: List[IssueEntry], entry: IssueEntry) -> None:
    target_value = entry.numeric_id
    for idx, existing in enumerate(entries):
        if target_value < existing.numeric_id:
            entries.insert(idx, entry)
            return
    entries.append(entry)


def build_batches(entries: List[IssueEntry]) -> Dict[int, List[IssueEntry]]:
    batches: Dict[int, List[IssueEntry]] = {}
    for idx, entry in enumerate(entries):
        batch_num = idx // BATCH_SIZE + 1
        batches.setdefault(batch_num, []).append(entry)
    return batches


def render_batch(batch_index: int, batch_entries: List[IssueEntry]) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    segments = [
        f"# {LINEAR_TEAM_NAME} - Issue Batch {batch_index}\n\n",
        f"_Generated: {timestamp}_\n\n",
        "---\n\n",
    ]
    segments.extend(entry.content for entry in batch_entries)
    return "".join(segments)


def update_status_doc(
    status_text: str,
    new_timestamp: datetime,
    summary_line: str,
    timestamp_label: str = "lastSyncTimestamp",
) -> None:
    new_ts_str = format_iso_timestamp(new_timestamp)

    lines = status_text.splitlines()
    label_token = f"`{timestamp_label}`"
    for idx, line in enumerate(lines):
        if label_token in line:
            lines[idx] = re.sub(
                rf"`{timestamp_label}`:\s*[0-9T:\-]+Z",
                f"`{timestamp_label}`: {new_ts_str}",
                line,
            )
            break
    else:
        raise LinearSyncError(f"Failed to locate `{timestamp_label}` in status doc.")

    try:
        daily_idx = lines.index("## Daily Summaries")
    except ValueError as exc:
        raise LinearSyncError("Could not locate '## Daily Summaries' section.") from exc

    insert_idx = daily_idx + 1
    while insert_idx < len(lines) and lines[insert_idx].strip() == "":
        insert_idx += 1

    # Remove placeholder or overwrite existing entry
    if insert_idx < len(lines) and lines[insert_idx].strip().startswith("- "):
        lines[insert_idx] = summary_line
        # Drop any additional summary lines to keep only the latest entry visible
        remove_idx = insert_idx + 1
        while (
            remove_idx < len(lines)
            and lines[remove_idx].strip()
            and lines[remove_idx].lstrip().startswith("- ")
        ):
            lines.pop(remove_idx)
        # Trim trailing blank lines within this section
        while remove_idx < len(lines) and lines[remove_idx].strip() == "":
            lines.pop(remove_idx)
    else:
        lines.insert(insert_idx, summary_line)

    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def summarize_changes(
    updates: List[str], new_issues: List[str], rewritten_files: List[Path]
) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts: List[str] = []
    if updates:
        display = ", ".join(sorted(updates)[:6])
        if len(updates) > 6:
            display += ", …"
        parts.append(f"{len(updates)} updated ({display})")
    if new_issues:
        display = ", ".join(sorted(new_issues)[:6])
        if len(new_issues) > 6:
            display += ", …"
        parts.append(f"{len(new_issues)} new ({display})")
    if not parts:
        parts.append("no changes")
    files_part = ""
    if rewritten_files:
        rel_files = [str(path.relative_to(REPO_ROOT)) for path in rewritten_files]
        files_part = f" → touched {', '.join(rel_files)}"
    return f"- {today}: {', '.join(parts)}{files_part}"


def main() -> None:
    if not LINEAR_API_KEY:
        raise LinearSyncError("LINEAR_API_KEY is not set.")

    status_text, last_sync_dt = parse_status_doc()
    print(f"Last sync timestamp: {format_iso_timestamp(last_sync_dt)}")

    team_id = get_team_id()
    print(f"Using team id: {team_id}")

    updated_issues = fetch_updated_issues(team_id, last_sync_dt)
    print(f"Found {len(updated_issues)} issue(s) updated since last sync.")

    entries, existing_batches = load_existing_entries()
    entry_map = {entry.identifier: entry for entry in entries}

    touched_identifiers: List[str] = []
    new_identifiers: List[str] = []
    latest_updated_at = last_sync_dt

    for issue in updated_issues:
        identifier = issue["identifier"]
        comments = fetch_comments(issue["id"])
        issue_markdown = format_issue(issue, comments)
        issue_entry = IssueEntry(identifier=identifier, content=issue_markdown)

        updated_at = parse_iso_datetime(issue["updatedAt"])
        if updated_at > latest_updated_at:
            latest_updated_at = updated_at

        if identifier in entry_map:
            entry_map[identifier].content = issue_markdown
            touched_identifiers.append(identifier)
        else:
            insert_new_entry(entries, issue_entry)
            entry_map[identifier] = issue_entry
            new_identifiers.append(identifier)

    new_batches = build_batches(entries)

    # Determine existing batch identifiers for comparison
    existing_ids_by_batch = {
        idx: info.get("identifiers", []) for idx, info in existing_batches.items()
    }

    changed_batches: Dict[int, List[IssueEntry]] = {}
    for batch_num, batch_entries in new_batches.items():
        new_ids = [entry.identifier for entry in batch_entries]
        old_ids = existing_ids_by_batch.get(batch_num, [])
        if new_ids != old_ids or any(
            identifier in touched_identifiers or identifier in new_identifiers
            for identifier in new_ids
        ):
            changed_batches[batch_num] = batch_entries

    rewritten_files: List[Path] = []
    for batch_num, batch_entries in changed_batches.items():
        path = existing_batches.get(batch_num, {}).get("path") or (
            LINEAR_DIR / f"{LINEAR_BATCH_PREFIX}-{batch_num}.md"
        )
        content = render_batch(batch_num, batch_entries)
        path.write_text(content, encoding="utf-8")
        rewritten_files.append(path)
        print(f"Updated {path.relative_to(REPO_ROOT)}")

    # Remove trailing batch files if the new count shrank
    new_batch_count = len(new_batches)
    for batch_num, info in existing_batches.items():
        if batch_num > new_batch_count and info["path"].exists():
            info["path"].unlink()
            print(f"Removed stale batch file {info['path'].relative_to(REPO_ROOT)}")

    summary_line = summarize_changes(touched_identifiers, new_identifiers, rewritten_files)

    # Ensure timestamp moves forward even if no updates were fetched
    final_timestamp = max(latest_updated_at, datetime.now(timezone.utc))
    update_status_doc(status_text, final_timestamp, summary_line)
    print("Status doc updated.")
    print(summary_line.replace("- ", "Summary: "))


if __name__ == "__main__":
    try:
        main()
    except LinearSyncError as exc:
        print(f"Sync failed: {exc}")
        sys.exit(1)
    except requests.HTTPError as exc:
        print(f"HTTP error while talking to Linear: {exc}")
        sys.exit(1)

