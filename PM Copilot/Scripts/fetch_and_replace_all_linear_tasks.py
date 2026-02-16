#!/usr/bin/env python3
"""
Fetch Linear tasks from a team and convert to markdown.
Groups tasks in batches of 50 per file.
Set LINEAR_API_KEY and optionally LINEAR_TEAM_NAME, LINEAR_BATCH_PREFIX, LINEAR_OUTPUT_DIR in environment.
"""

import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

# Configuration: set LINEAR_API_KEY and optionally LINEAR_TEAM_NAME in environment
LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_TEAM_NAME = os.environ.get("LINEAR_TEAM_NAME", "My Team")
LINEAR_BATCH_PREFIX = os.environ.get("LINEAR_BATCH_PREFIX", "Issues-Batch")

# Directory for Linear tasks (override with LINEAR_OUTPUT_DIR if needed)
linear_dir = Path(os.environ.get("LINEAR_OUTPUT_DIR", "output/Linear"))
linear_dir.mkdir(parents=True, exist_ok=True)

STATUS_PATH = linear_dir / "Linear-Sync-Status.md"

# Headers for Linear API
headers = {
    "Authorization": LINEAR_API_KEY,
    "Content-Type": "application/json"
}

def make_graphql_request(query, variables=None):
    """Make a GraphQL request to Linear API"""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    response = requests.post(LINEAR_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def get_team_id():
    """Get the Linear team ID by name (from LINEAR_TEAM_NAME)."""
    query = """
    query {
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
    team_name = LINEAR_TEAM_NAME
    for team in teams:
        if team["name"] == team_name:
            return team["id"]
    return None

def fetch_all_issues(team_id):
    """Fetch all issues for the team with pagination"""
    print(f"Fetching issues from {LINEAR_TEAM_NAME} team...")
    
    query = """
    query GetIssues($teamId: ID!, $after: String) {
        issues(
            filter: { team: { id: { eq: $teamId } } }
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
                state {
                    name
                }
                priority
                assignee {
                    name
                }
                creator {
                    name
                }
                createdAt
                updatedAt
                dueDate
                team {
                    name
                }
                cycle {
                    name
                }
                project {
                    name
                }
                branchName
                labels {
                    nodes {
                        name
                    }
                }
            }
        }
    }
    """
    
    issues = []
    has_next_page = True
    cursor = None
    
    while has_next_page:
        variables = {"teamId": team_id}
        if cursor:
            variables["after"] = cursor
        
        result = make_graphql_request(query, variables)
        data = result["data"]["issues"]
        
        issues.extend(data["nodes"])
        has_next_page = data["pageInfo"]["hasNextPage"]
        cursor = data["pageInfo"]["endCursor"]
        
        print(f"Fetched {len(issues)} issues so far...")
    
    print(f"Found {len(issues)} total issues")
    return issues

def fetch_comments(issue_id):
    """Fetch comments for an issue"""
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
        if result.get("data") and result["data"].get("issue"):
            return result["data"]["issue"]["comments"]["nodes"]
    except Exception as e:
        print(f"Error fetching comments for issue {issue_id}: {e}")
    
    return []

def format_issue(issue, comments):
    """Format a single issue as markdown"""
    lines = []
    
    # Title
    lines.append(f"# {issue['identifier']}: {issue['title']}\n")
    
    # Metadata
    metadata = []
    if issue.get('state'):
        metadata.append(f"**Status:** {issue['state']['name']}")
    if issue.get('labels') and issue['labels'].get('nodes'):
        label_names = [label['name'] for label in issue['labels']['nodes']]
        if label_names:
            metadata.append(f"**Labels:** {', '.join(label_names)}")
    if issue.get('priority'):
        metadata.append(f"**Priority:** {issue['priority']}")
    if issue.get('assignee'):
        metadata.append(f"**Assignee:** {issue['assignee']['name']}")
    if issue.get('creator'):
        metadata.append(f"**Created By:** {issue['creator']['name']}")
    if issue.get('createdAt'):
        metadata.append(f"**Created:** {issue['createdAt'].split('T')[0]}")
    if issue.get('updatedAt'):
        metadata.append(f"**Updated:** {issue['updatedAt'].split('T')[0]}")
    if issue.get('dueDate'):
        metadata.append(f"**Due Date:** {issue['dueDate'].split('T')[0]}")
    if issue.get('team'):
        metadata.append(f"**Team:** {issue['team']['name']}")
    if issue.get('cycle'):
        metadata.append(f"**Cycle:** {issue['cycle']['name']}")
    if issue.get('project'):
        metadata.append(f"**Project:** {issue['project']['name']}")
    if issue.get('url'):
        metadata.append(f"**Linear URL:** {issue['url']}")
    if issue.get('branchName'):
        metadata.append(f"**Git Branch:** {issue['branchName']}")
    
    if metadata:
        lines.append(" ".join(metadata) + "\n")
    
    lines.append("\n## Description\n\n")
    
    # Description
    if issue.get('description'):
        lines.append(issue['description'] + "\n")
    else:
        lines.append("_No description provided._\n")
    
    # Comments
    lines.append("\n## Comments\n\n")
    if comments:
        for comment in comments:
            author_name = comment['user']['name'] if comment.get('user') else "Unknown"
            created_at = comment['createdAt'].split('T')[0] if comment.get('createdAt') else ""
            body = comment['body'] if comment.get('body') else ""
            
            lines.append(f"### {author_name} - {created_at}\n\n")
            lines.append(f"{body}\n\n")
    else:
        lines.append("_No comments yet._\n")
    
    lines.append("\n---\n\n")
    
    return "\n".join(lines)


def parse_iso_datetime(value):
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso_timestamp(dt):
    return (
        dt.astimezone(timezone.utc)
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def update_status_last_sync(new_timestamp, timestamp_label="lastSyncTimestamp"):
    if not STATUS_PATH.exists():
        print(f"Warning: status doc not found at {STATUS_PATH}, skipping timestamp update.")
        return
    text = STATUS_PATH.read_text(encoding="utf-8")
    pattern = rf"(`{timestamp_label}`:\s*)([0-9T:\-]+Z)"
    new_ts_str = format_iso_timestamp(new_timestamp)
    updated_text, replacements = re.subn(pattern, rf"\1{new_ts_str}", text, count=1)
    if replacements != 1:
        print("Warning: could not update last sync timestamp in status doc.")
        return
    STATUS_PATH.write_text(updated_text, encoding="utf-8")
    print(f"Status doc updated with last sync timestamp {new_ts_str}.")


def get_numeric_identifier(identifier):
    """Extract numeric portion from identifier (e.g., 'ISSUE-504' → 504)
    Returns a large number if no numeric part is found to sort such items to the end"""
    if not identifier:
        return float('inf')
    
    # Try to find numeric part after the last hyphen or dash
    parts = re.split(r'[-_]', identifier)
    for part in reversed(parts):
        # Extract digits from the part
        match = re.search(r'\d+', part)
        if match:
            return int(match.group())
    
    # If no numeric part found, return inf to sort to end
    return float('inf')

def main():
    """Main function to fetch and save all issues"""
    
    if not LINEAR_API_KEY:
        print("Error: LINEAR_API_KEY environment variable not set")
        return
    
    # Get team ID
    team_id = get_team_id()
    if not team_id:
        print(f"Error: Could not find team '{LINEAR_TEAM_NAME}'")
        return
    print(f"Found team: {team_id}")
    
    # Fetch all issues
    issues = fetch_all_issues(team_id)
    
    if not issues:
        print("No issues found")
        return
    
    # Sort issues by numeric identifier (e.g., ISSUE-504, ISSUE-505)
    print(f"\nSorting {len(issues)} issues by identifier...")
    issues.sort(key=lambda issue: get_numeric_identifier(issue.get('identifier', '')))
    
    # Process in batches of 50
    batch_size = 50
    num_batches = (len(issues) + batch_size - 1) // batch_size
    
    print(f"\nProcessing {len(issues)} issues in {num_batches} batch(es) of {batch_size}...")
    
    for batch_num in range(num_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(issues))
        batch_issues = issues[start_idx:end_idx]
        
        batch_file = linear_dir / f"{LINEAR_BATCH_PREFIX}-{batch_num + 1}.md"
        print(f"Processing batch {batch_num + 1}/{num_batches}: {len(batch_issues)} issues...")
        with open(batch_file, 'w', encoding='utf-8') as f:
            f.write(f"# {LINEAR_TEAM_NAME} - Issue Batch {batch_num + 1}\n\n")
            f.write(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n")
            f.write(f"---\n\n")
            
            for i, issue in enumerate(batch_issues, 1):
                print(f"  [{i}/{len(batch_issues)}] Processing {issue['identifier']}...", end=' ')
                
                # Fetch comments for each issue
                comments = fetch_comments(issue['id'])
                issue_markdown = format_issue(issue, comments)
                f.write(issue_markdown)
                
                print("✓")
        
        print(f"Saved {batch_file}")
    
    print(f"\n✓ Completed! Saved {num_batches} batch file(s) with {len(issues)} total issues")

    latest_updated = None
    for issue in issues:
        issue_updated = parse_iso_datetime(issue.get("updatedAt"))
        if not issue_updated:
            continue
        if latest_updated is None or issue_updated > latest_updated:
            latest_updated = issue_updated

    if latest_updated is None:
        latest_updated = datetime.now(timezone.utc)

    update_status_last_sync(latest_updated)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

