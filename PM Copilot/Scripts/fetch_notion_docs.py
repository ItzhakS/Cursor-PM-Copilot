#!/usr/bin/env python3
"""
Fetch Notion pages and convert to markdown for the RAG system.

Supports two modes:
1. Auto-discovery mode: Automatically discovers and syncs all databases and pages.
2. Manual mode: Fetches specific databases/pages by ID (legacy mode).

Processes in small batches to avoid API timeouts.
Also updates the Notion sync status doc with the last full-sync timestamp.
"""

from __future__ import annotations

import os
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

# Repository paths: set NOTION_OUTPUT_DIR to override where markdown is written
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
NOTION_DIR = Path(os.environ.get("NOTION_OUTPUT_DIR", REPO_ROOT / "output" / "Notion"))
NOTION_DIR.mkdir(parents=True, exist_ok=True)

STATUS_PATH = NOTION_DIR / "SYNC_STATUS.md"

# Configuration: set NOTION_API_SECRET in environment (e.g. from Notion integration settings)
NOTION_API_SECRET = os.environ.get("NOTION_API_SECRET", "")
NOTION_API_URL = "https://api.notion.com/v1"

# Headers for Notion API
headers = {
    "Authorization": f"Bearer {NOTION_API_SECRET}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Batch size for processing pages
BATCH_SIZE = 10

def make_api_request(method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None):
    """Make a request to Notion API"""
    url = f"{NOTION_API_URL}/{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 429:
            # Rate limit - wait and retry
            retry_after = int(response.headers.get("Retry-After", 1))
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            return make_api_request(method, endpoint, data, params)
        elif response.status_code == 400:
            # Bad request - show error details
            try:
                error_data = response.json()
                error_msg = error_data.get("message", "Bad Request")
                error_code = error_data.get("code", "unknown")
                print(f"  API Error: {error_code} - {error_msg}")
                if "object_id" in error_msg.lower() or "invalid" in error_msg.lower():
                    print(f"  Tip: Check if the page ID is correct and the integration has access to this page")
            except:
                print(f"  Error response: {response.text[:200]}")
        raise

def format_page_id_with_dashes(page_id: str) -> str:
    """Format page ID with dashes in Notion format: 8-4-4-4-12"""
    # Remove existing dashes
    clean_id = page_id.replace("-", "")
    
    # Add dashes in format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    if len(clean_id) == 32:
        return f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"
    return clean_id

def extract_page_id_from_url(url: str) -> str:
    """Extract page ID from Notion URL and format with dashes"""
    # Format: https://www.notion.so/{page-id}?v=...
    # Or: https://www.notion.so/{page-id}
    if not url:
        return ""
    
    # Remove https://www.notion.so/ or https://notion.so/
    url = url.replace("https://www.notion.so/", "").replace("https://notion.so/", "")
    
    # Extract the page ID (32 characters, possibly with dashes)
    # Remove query parameters
    if "?" in url:
        url = url.split("?")[0]
    
    # Remove dashes first to get clean ID
    page_id = url.replace("-", "")
    
    # Format with dashes for Notion API
    return format_page_id_with_dashes(page_id)

def search_objects(object_type: str = "page", page_size: int = 100):
    """Search for objects (pages or databases) in Notion workspace
    
    Args:
        object_type: "page" or "database"
        page_size: Number of results per page (max 100)
    
    Returns:
        List of objects found
    """
    print(f"Searching for {object_type}s...")
    
    results = []
    has_more = True
    start_cursor = None
    
    while has_more:
        data = {
            "filter": {
                "value": object_type,
                "property": "object"
            },
            "page_size": min(page_size, 100),
            "sort": {
                "direction": "descending",
                "timestamp": "last_edited_time"
            }
        }
        
        if start_cursor:
            data["start_cursor"] = start_cursor
        
        try:
            response = make_api_request("POST", "search", data)
            batch_results = response.get("results", [])
            results.extend(batch_results)
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
            print(f"  Found {len(results)} {object_type}s so far...")
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"Error searching for {object_type}s: {e}")
            break
    
    print(f"Found {len(results)} total {object_type}s")
    return results

def search_pages(query: str = None, filter_properties: Optional[List[str]] = None, page_size: int = 100):
    """Search for pages in Notion workspace
    
    Note: Notion API doesn't support text search in search endpoint.
    This function returns all accessible pages, then filters by title client-side.
    For better results, consider using specific page IDs or parent page IDs.
    """
    all_pages = search_objects("page", page_size)
    
    # Filter by query if provided
    if query:
        query_lower = query.lower()
        filtered = []
        for page in all_pages:
            title = get_page_title(page).lower()
            if query_lower in title:
                filtered.append(page)
        return filtered
    
    return all_pages

def get_database_title(database: Dict) -> str:
    """Extract database title from Notion database object"""
    title = database.get("title", [])
    if title and isinstance(title, list) and len(title) > 0:
        return extract_text_from_rich_text(title)
    return "Untitled Database"

def discover_all_databases() -> List[Dict]:
    """Discover all databases accessible to the integration"""
    print("\n" + "="*60)
    print("DISCOVERING ALL DATABASES")
    print("="*60 + "\n")
    
    databases = search_objects("database")
    
    print(f"\n✓ Discovered {len(databases)} databases")
    for db in databases:
        db_id = db.get("id", "")
        db_title = get_database_title(db)
        print(f"  - {db_title} ({db_id[:8]}...)")
    
    return databases

def discover_root_pages() -> List[Dict]:
    """Discover all root-level pages (pages not in databases)"""
    print("\n" + "="*60)
    print("DISCOVERING ROOT-LEVEL PAGES")
    print("="*60 + "\n")
    
    all_pages = search_objects("page")
    
    # Filter for root-level pages (parent is workspace, not a database or page)
    root_pages = []
    for page in all_pages:
        parent = page.get("parent", {})
        parent_type = parent.get("type", "")
        
        # Root pages have workspace as parent, or are top-level pages
        if parent_type == "workspace":
            root_pages.append(page)
    
    print(f"\n✓ Discovered {len(root_pages)} root-level pages")
    for page in root_pages[:10]:  # Show first 10
        page_title = get_page_title(page)
        print(f"  - {page_title}")
    if len(root_pages) > 10:
        print(f"  ... and {len(root_pages) - 10} more")
    
    return root_pages

def get_all_child_pages(parent_page_id: str, visited: set = None) -> List[Dict]:
    """Recursively get all child pages under a parent page"""
    if visited is None:
        visited = set()
    
    # Ensure page ID has dashes
    parent_id_formatted = format_page_id_with_dashes(parent_page_id.replace("-", ""))
    parent_id_clean = parent_id_formatted.replace("-", "")
    
    if parent_id_clean in visited:
        return []
    
    visited.add(parent_id_clean)
    
    print(f"Fetching children of page {parent_id_formatted[:8]}...")
    
    # Get blocks from parent page (API needs formatted ID with dashes)
    blocks = get_page_blocks(parent_id_formatted)
    
    child_pages = []
    
    for block in blocks:
        if block.get("type") == "child_page":
            child_id = block.get("id", "")
            # Keep dashes for API calls
            child_id_formatted = format_page_id_with_dashes(child_id.replace("-", ""))
            child_id_clean = child_id_formatted.replace("-", "")
            
            if child_id_clean not in visited:
                try:
                    child_page = make_api_request("GET", f"pages/{child_id_formatted}")
                    child_pages.append(child_page)
                    
                    # Recursively get children of this child
                    grandchildren = get_all_child_pages(child_id_formatted, visited)
                    child_pages.extend(grandchildren)
                    
                    time.sleep(0.3)  # Rate limiting
                except Exception as e:
                    print(f"    Error fetching child page {child_id_formatted[:8]}: {e}")
    
    return child_pages

def get_page_blocks(page_id: str):
    """Fetch all blocks for a page"""
    # Ensure page ID has dashes
    page_id_formatted = format_page_id_with_dashes(page_id.replace("-", ""))
    
    blocks = []
    has_more = True
    start_cursor = None
    
    while has_more:
        params = {"page_size": 100}
        if start_cursor:
            params["start_cursor"] = start_cursor
        
        try:
            response = make_api_request("GET", f"blocks/{page_id_formatted}/children", params=params)
            blocks.extend(response.get("results", []))
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            time.sleep(0.3)  # Rate limiting
        except Exception as e:
            print(f"Error fetching blocks for {page_id_formatted}: {e}")
            break
    
    return blocks

def get_page_content(page_id: str):
    """Fetch full page content including blocks"""
    # Ensure page ID has dashes
    page_id_formatted = format_page_id_with_dashes(page_id.replace("-", ""))
    
    try:
        page_data = make_api_request("GET", f"pages/{page_id_formatted}")
        blocks = get_page_blocks(page_id_formatted)
        return page_data, blocks
    except Exception as e:
        print(f"Error fetching page {page_id_formatted}: {e}")
        return None, []

def extract_text_from_rich_text(rich_text_array: List[Dict]) -> str:
    """Extract plain text from Notion rich_text array"""
    if not rich_text_array:
        return ""
    
    text_parts = []
    for item in rich_text_array:
        if item.get("type") == "text":
            text_parts.append(item.get("text", {}).get("content", ""))
        elif item.get("type") == "mention":
            mention = item.get("mention", {})
            if mention.get("type") == "page":
                text_parts.append(f"[{item.get('plain_text', '')}]")
            else:
                text_parts.append(item.get("plain_text", ""))
        else:
            text_parts.append(item.get("plain_text", ""))
    
    return "".join(text_parts)

def blocks_to_markdown(blocks: List[Dict], indent_level: int = 0) -> str:
    """Convert Notion blocks to markdown"""
    markdown_lines = []
    indent = "  " * indent_level
    
    for block in blocks:
        block_type = block.get("type")
        
        if block_type == "paragraph":
            text = extract_text_from_rich_text(block.get("paragraph", {}).get("rich_text", []))
            if text.strip():
                markdown_lines.append(f"{indent}{text}\n")
        elif block_type == "heading_1":
            text = extract_text_from_rich_text(block.get("heading_1", {}).get("rich_text", []))
            if text.strip():
                markdown_lines.append(f"{indent}# {text}\n\n")
        elif block_type == "heading_2":
            text = extract_text_from_rich_text(block.get("heading_2", {}).get("rich_text", []))
            if text.strip():
                markdown_lines.append(f"{indent}## {text}\n\n")
        elif block_type == "heading_3":
            text = extract_text_from_rich_text(block.get("heading_3", {}).get("rich_text", []))
            if text.strip():
                markdown_lines.append(f"{indent}### {text}\n\n")
        elif block_type == "bulleted_list_item":
            text = extract_text_from_rich_text(block.get("bulleted_list_item", {}).get("rich_text", []))
            if text.strip():
                markdown_lines.append(f"{indent}- {text}\n")
        elif block_type == "numbered_list_item":
            text = extract_text_from_rich_text(block.get("numbered_list_item", {}).get("rich_text", []))
            if text.strip():
                markdown_lines.append(f"{indent}1. {text}\n")
        elif block_type == "to_do":
            text = extract_text_from_rich_text(block.get("to_do", {}).get("rich_text", []))
            checked = block.get("to_do", {}).get("checked", False)
            checkbox = "[x]" if checked else "[ ]"
            if text.strip():
                markdown_lines.append(f"{indent}{checkbox} {text}\n")
        elif block_type == "quote":
            text = extract_text_from_rich_text(block.get("quote", {}).get("rich_text", []))
            if text.strip():
                markdown_lines.append(f"{indent}> {text}\n\n")
        elif block_type == "code":
            text = extract_text_from_rich_text(block.get("code", {}).get("rich_text", []))
            language = block.get("code", {}).get("language", "")
            if text.strip():
                markdown_lines.append(f"{indent}```{language}\n{indent}{text}\n{indent}```\n\n")
        elif block_type == "divider":
            markdown_lines.append(f"{indent}---\n\n")
        elif block_type == "table":
            # Handle tables - simplified version
            markdown_lines.append(f"{indent}[Table block - content not fully parsed]\n\n")
        
        # Handle children blocks recursively
        if block.get("has_children"):
            child_blocks = get_page_blocks(block.get("id"))
            if child_blocks:
                child_markdown = blocks_to_markdown(child_blocks, indent_level + 1)
                markdown_lines.append(child_markdown)
    
    return "".join(markdown_lines)

def get_page_title(page: Dict) -> str:
    """Extract page title from Notion page object"""
    # For regular pages, check properties
    properties = page.get("properties", {})
    
    if properties:
        # Look for title property in database pages
        for prop_name, prop_data in properties.items():
            if prop_data.get("type") == "title":
                title_array = prop_data.get("title", [])
                if title_array:
                    return extract_text_from_rich_text(title_array)
        
        # Fallback: look for any property with name-like patterns
        for prop_name in ["Name", "Title", "Page"]:
            if prop_name in properties:
                prop_data = properties[prop_name]
                if prop_data.get("type") == "title":
                    title_array = prop_data.get("title", [])
                    if title_array:
                        return extract_text_from_rich_text(title_array)
    
    # For regular pages (not database entries), try to get title from first heading block
    # or use page ID as fallback
    page_id = page.get("id", "")
    if not properties and page_id:
        # This is likely a regular page, we'll try to get title from content when we fetch it
        # For now, use a placeholder
        return f"Page_{page_id[:8]}"
    
    return "Untitled Page"

def sanitize_filename(filename: str, *, replace_spaces: bool = False) -> str:
    """Sanitize a string for use as a filename or directory name."""
    if filename is None:
        return ""
    
    # Remove characters that the filesystem cannot handle
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)
    
    # Normalise whitespace
    filename = filename.strip()
    filename = re.sub(r"\s+", " " if not replace_spaces else "_", filename)
    
    if replace_spaces:
        filename = filename.replace(" ", "_")
    
    # Avoid empty names
    if not filename:
        return ""
    
    # Limit length to stay well under filesystem limits
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename


def build_page_filename(title: str, page_id_clean: str) -> str:
    """Create a deterministic filename for a page based on its title and ID."""
    stem = sanitize_filename(title)
    if not stem:
        stem = f"page_{page_id_clean[:8]}"
    else:
        stem = f"{stem}__{page_id_clean[:8]}"
    return f"{stem}.md"


def purge_duplicate_files(output_dir: Path, target_path: Path, page_id_clean: str) -> None:
    """Remove legacy duplicate exports for the same page ID within a directory."""
    notion_id_token = page_id_clean.lower()
    for existing in output_dir.glob("*.md"):
        if existing == target_path:
            continue
        try:
            with existing.open("r", encoding="utf-8", errors="ignore") as handle:
                snippet = handle.read(2048)
        except OSError:
            continue
        
        if notion_id_token in snippet.replace("-", "").lower():
            try:
                existing.unlink()
                print(f"    ℹ Removed duplicate export: {existing.relative_to(REPO_ROOT)}")
            except OSError:
                print(f"    ⚠ Could not remove legacy duplicate file: {existing}")

def format_page_markdown(page: Dict, blocks: List[Dict], page_url: str) -> str:
    """Format a complete page as markdown"""
    title = get_page_title(page)
    created_time = page.get("created_time", "")
    last_edited_time = page.get("last_edited_time", "")
    
    lines = []
    
    # Header with metadata
    lines.append(f"# {title}\n\n")
    lines.append(f"**Notion URL:** {page_url}\n")
    if created_time:
        lines.append(f"**Created:** {created_time.split('T')[0]}\n")
    if last_edited_time:
        lines.append(f"**Last Edited:** {last_edited_time.split('T')[0]}\n")
    lines.append("\n---\n\n")
    
    # Page content
    content = blocks_to_markdown(blocks)
    lines.append(content)
    
    return "".join(lines)

def save_page(page: Dict, output_dir: Path, page_url: str, *, overwrite: bool = False) -> Optional[Path]:
    """Fetch and save a single page.

    Args:
        page: Notion page object (from query/search).
        output_dir: Directory to write markdown file.
        page_url: URL for metadata header.
        overwrite: If True, overwrite existing file path instead of creating a new suffix.

    Returns:
        Path to the saved file, or None if fetch failed.
    """
    page_id = page.get("id", "")
    # Format page ID with dashes for API calls
    page_id_formatted = format_page_id_with_dashes(page_id.replace("-", ""))
    page_id_clean = page_id.replace("-", "")
    title = get_page_title(page)
    
    print(f"  Fetching page: {title}...")
    
    page_data, blocks = get_page_content(page_id_formatted)
    if not page_data:
        print(f"    ✗ Failed to fetch page")
        return False
    
    # Format as markdown
    markdown_content = format_page_markdown(page_data, blocks, page_url)
    
    # Save to file
    filename = build_page_filename(title, page_id_clean)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / filename
    
    # Remove legacy duplicates so the filename stays stable across runs
    purge_duplicate_files(output_dir, filepath, page_id_clean)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"    ✓ Saved: {filepath.relative_to(REPO_ROOT)}")
    return filepath

def process_pages_from_list(stage_name: str, pages: List[Dict], output_dir: Path):
    """Process pages from a provided list (e.g., from database query)"""
    print(f"\n{'='*60}")
    print(f"STAGE: {stage_name}")
    print(f"{'='*60}\n")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Remove duplicates by page ID
    unique_pages = {}
    for page in pages:
        page_id = page.get("id")
        if page_id:
            unique_pages[page_id] = page
    
    pages_list = list(unique_pages.values())
    
    print(f"Processing {len(pages_list)} unique pages in batches of {BATCH_SIZE}...\n")
    
    # Process in batches
    for batch_start in range(0, len(pages_list), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(pages_list))
        batch = pages_list[batch_start:batch_end]
        
        print(f"\nBatch {batch_start // BATCH_SIZE + 1} ({len(batch)} pages):")
        
        for page in batch:
            page_id = page.get("id")
            page_url = page.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")
            save_page(page, output_dir, page_url)
            time.sleep(0.5)  # Rate limiting between pages
        
        print(f"Completed batch {batch_start // BATCH_SIZE + 1}")
        time.sleep(2)  # Longer pause between batches
    
    print(f"\n✓ Stage '{stage_name}' complete! Saved {len(pages_list)} pages to {output_dir}")
    return len(pages_list)

def query_database(database_id: str):
    """Query a database to get all its pages"""
    database_id_formatted = format_page_id_with_dashes(database_id.replace("-", ""))
    
    print(f"Querying database: {database_id_formatted[:8]}...")
    
    all_pages = []
    has_more = True
    start_cursor = None
    
    while has_more:
        data = {
            "page_size": 100
        }
        
        if start_cursor:
            data["start_cursor"] = start_cursor
        
        try:
            response = make_api_request("POST", f"databases/{database_id_formatted}/query", data)
            pages = response.get("results", [])
            all_pages.extend(pages)
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
            print(f"  Found {len(all_pages)} pages so far...")
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"Error querying database: {e}")
            break
    
    print(f"Total pages in database: {len(all_pages)}")
    return all_pages

def build_page_hierarchy(pages: List[Dict]) -> Dict:
    """Build hierarchy from pages using ancestor paths"""
    # Create a map of page_id -> page data
    pages_map = {}
    root_pages = []
    
    for page in pages:
        page_id = page.get("id", "")
        parent = page.get("parent", {})
        parent_type = parent.get("type", "")
        
        pages_map[page_id] = {
            "page": page,
            "children": []
        }
        
        # If parent is workspace or a database, it's a root page
        if parent_type in ["workspace", "database_id"]:
            root_pages.append(page_id)
        elif parent_type == "page_id":
            parent_id = parent.get("page_id", "")
            # We'll link children to parents after building the map
            pass
    
    # Build parent-child relationships
    for page_id, page_data in pages_map.items():
        page = page_data["page"]
        parent = page.get("parent", {})
        parent_type = parent.get("type", "")
        
        if parent_type == "page_id":
            parent_id = parent.get("page_id", "")
            if parent_id in pages_map:
                pages_map[parent_id]["children"].append(page_id)
            else:
                # Parent not in our set, treat as root
                root_pages.append(page_id)
    
    return {
        "pages_map": pages_map,
        "root_pages": root_pages
    }

def fetch_wiki(page_url: str = None, page_id: str = None):
    """Stage 1a: Fetch a wiki database or page and all its pages. Pass page_url or page_id (or set NOTION_WIKI_PAGE_ID)."""
    print("\n" + "="*60)
    print("STAGE 1a: WIKI")
    print("="*60 + "\n")
    page_id = page_id or (extract_page_id_from_url(page_url) if page_url else None) or os.environ.get("NOTION_WIKI_PAGE_ID", "")
    if not page_id:
        print("Skipping: no wiki page_id or page_url (set NOTION_WIKI_PAGE_ID or pass page_url/page_id)")
        return
    wiki_dir = NOTION_DIR / "Wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    
    # Format page ID with dashes for API
    page_id_formatted = format_page_id_with_dashes(page_id.replace("-", ""))
    
    print(f"Fetching wiki database: {page_id_formatted[:8]}...")
    print(f"  Full database ID: {page_id_formatted}")
    
    try:
        # Try to fetch as database first
        try:
            database = make_api_request("GET", f"databases/{page_id_formatted}")
            print(f"  Database found: {database.get('title', [{}])[0].get('plain_text', 'Unknown') if database.get('title') else 'Unknown'}")
            
            # Query the database to get all pages
            print("\nQuerying database for pages...")
            database_pages = query_database(page_id_formatted)
            
            if not database_pages:
                print("No pages found in database")
                return
            
            # Build hierarchy from ancestor paths
            print("\nBuilding page hierarchy...")
            hierarchy = build_page_hierarchy(database_pages)
            
            print(f"\nTotal wiki pages to process: {len(database_pages)}")
            
            # Process pages in batches (using IDs only, no search)
            process_pages_from_list("Wiki", database_pages, wiki_dir)
            
        except requests.exceptions.HTTPError as e:
            if "database" in str(e).lower():
                # It's not a database, try as a regular page
                print("  Not a database, trying as regular page...")
                wiki_page = make_api_request("GET", f"pages/{page_id_formatted}")
                page_url = wiki_page.get("url", f"https://www.notion.so/{page_id_formatted}")
                
                print(f"  Main page: {get_page_title(wiki_page)}")
                
                # Save the main page
                save_page(wiki_page, wiki_dir, page_url)
                
                # Get all child pages recursively
                print("\nFetching all child pages...")
                child_pages = get_all_child_pages(page_id_formatted)
                
                print(f"\nFound {len(child_pages)} child pages")
                
                # Save all child pages
                for child_page in child_pages:
                    child_url = child_page.get("url", "")
                    save_page(child_page, wiki_dir, child_url)
                
                print(f"\n✓ Wiki saved to {wiki_dir}")
                print(f"  Total pages: {len(child_pages) + 1} (1 main + {len(child_pages)} children)")
        
    except Exception as e:
        print(f"Error fetching wiki: {e}")
        import traceback
        traceback.print_exc()

def fetch_ceo_pages(database_url: str = None, database_id: str = None):
    """Stage 1b: Fetch leadership pages from database or page IDs"""
    output_dir = NOTION_DIR / "Leadership"
    
    if database_url or database_id:
        # Fetch from database
        if database_url:
            db_id = extract_page_id_from_url(database_url)
        else:
            db_id = database_id
        
        db_id_formatted = format_page_id_with_dashes(db_id.replace("-", ""))
        
        try:
            # Try as database first
            database = make_api_request("GET", f"databases/{db_id_formatted}")
            database_pages = query_database(db_id_formatted)
            process_pages_from_list("Leadership", database_pages, output_dir)
        except:
            # If not a database, skip for now
            print("  No database URL/ID provided, skipping leadership pages")
    else:
        print("  Skipping leadership pages - no database URL/ID provided")
        print("  To fetch leadership pages, provide database_url or database_id parameter")

def fetch_product_pages(database_url: str = None, database_id: str = None):
    """Stage 2: Fetch Product pages from database. Pass database_url or database_id (or set NOTION_PRODUCT_DATABASE_ID)."""
    output_dir = NOTION_DIR / "Product"
    database_id = database_id or (extract_page_id_from_url(database_url) if database_url else None) or os.environ.get("NOTION_PRODUCT_DATABASE_ID", "")
    if database_url or database_id:
        # Fetch from database
        if database_url:
            db_id = extract_page_id_from_url(database_url)
        else:
            db_id = database_id
        
        db_id_formatted = format_page_id_with_dashes(db_id.replace("-", ""))
        
        try:
            # Try as database first
            database = make_api_request("GET", f"databases/{db_id_formatted}")
            database_pages = query_database(db_id_formatted)
            process_pages_from_list("Product", database_pages, output_dir)
        except Exception as e:
            print(f"  Error fetching Product database: {e}")
            print("  Skipping Product pages")
    else:
        print("  Skipping Product pages - no database URL/ID provided")
        print("  To fetch Product pages, provide database_url or database_id parameter")

def fetch_operations_pages(database_url: str = None, database_id: str = None):
    """Stage 3a: Fetch Operations pages from database or page IDs"""
    output_dir = NOTION_DIR / "Operations"
    
    if database_url or database_id:
        # Fetch from database
        if database_url:
            db_id = extract_page_id_from_url(database_url)
        else:
            db_id = database_id
        
        db_id_formatted = format_page_id_with_dashes(db_id.replace("-", ""))
        
        try:
            # Try as database first
            database = make_api_request("GET", f"databases/{db_id_formatted}")
            database_pages = query_database(db_id_formatted)
            process_pages_from_list("Operations", database_pages, output_dir)
        except:
            # If not a database, skip for now
            print("  No database URL/ID provided, skipping Operations pages")
    else:
        print("  Skipping Operations pages - no database URL/ID provided")
        print("  To fetch Operations pages, provide database_url or database_id parameter")

def fetch_success_pages(database_url: str = None, database_id: str = None):
    """Stage 3b: Fetch Customer Success pages from database or page IDs"""
    output_dir = NOTION_DIR / "Customer Success"
    
    if database_url or database_id:
        # Fetch from database
        if database_url:
            db_id = extract_page_id_from_url(database_url)
        else:
            db_id = database_id
        
        db_id_formatted = format_page_id_with_dashes(db_id.replace("-", ""))
        
        try:
            # Try as database first
            database = make_api_request("GET", f"databases/{db_id_formatted}")
            database_pages = query_database(db_id_formatted)
            process_pages_from_list("Customer Success", database_pages, output_dir)
        except:
            # If not a database, skip for now
            print("  No database URL/ID provided, skipping Customer Success pages")
    else:
        print("  Skipping Customer Success pages - no database URL/ID provided")
        print("  To fetch Customer Success pages, provide database_url or database_id parameter")

def fetch_database(database: Dict, output_base_dir: Path = None):
    """Fetch all pages from a database and save them"""
    if output_base_dir is None:
        output_base_dir = NOTION_DIR
    
    database_id = database.get("id", "")
    database_id_formatted = format_page_id_with_dashes(database_id.replace("-", ""))
    database_title = get_database_title(database)
    
    # Create directory for this database
    db_dir_name = sanitize_filename(database_title)
    if not db_dir_name:
        db_dir_name = database_id_formatted.replace("-", "")
    output_dir = output_base_dir / db_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nProcessing database: {database_title}")
    print(f"  Database ID: {database_id_formatted[:8]}...")
    
    try:
        # Query database for all pages
        database_pages = query_database(database_id_formatted)
        
        if not database_pages:
            print(f"  No pages found in database")
            return 0
        
        # Process pages
        process_pages_from_list(database_title, database_pages, output_dir)
        return len(database_pages)
    except Exception as e:
        print(f"  Error processing database {database_title}: {e}")
        return 0

def fetch_root_page(page: Dict, output_base_dir: Path = None):
    """Fetch a root-level page and its children"""
    if output_base_dir is None:
        output_base_dir = NOTION_DIR
    
    page_id = page.get("id", "")
    page_id_formatted = format_page_id_with_dashes(page_id.replace("-", ""))
    page_title = get_page_title(page)
    page_url = page.get("url", f"https://www.notion.so/{page_id.replace('-', '')}")
    
    # Check if this page is a database (some databases appear as pages in search)
    parent = page.get("parent", {})
    parent_type = parent.get("type", "")
    
    # If parent is workspace, save to root pages directory
    if parent_type == "workspace":
        root_pages_dir = output_base_dir / "Root Pages"
        root_pages_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\nProcessing root page: {page_title}")
        
        try:
            # Save the page itself
            save_page(page, root_pages_dir, page_url)
            
            # Get all child pages recursively
            child_pages = get_all_child_pages(page_id_formatted)
            
            # Save child pages
            for child_page in child_pages:
                child_url = child_page.get("url", "")
                save_page(child_page, root_pages_dir, child_url)
            
            return len(child_pages) + 1
        except Exception as e:
            print(f"  Error processing root page {page_title}: {e}")
            return 0
    
    return 0

def sync_all_notion_content(auto_discover: bool = True):
    """Main sync function that discovers and syncs all Notion content"""
    print("="*60)
    print("NOTION FULL SYNC - AUTO-DISCOVERY MODE")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    total_pages_synced = 0
    databases_processed = 0
    root_pages_processed = 0
    
    try:
        # Step 1: Discover and sync all databases
        databases = discover_all_databases()
        
        print(f"\n{'='*60}")
        print(f"SYNCING {len(databases)} DATABASES")
        print(f"{'='*60}\n")
        
        for i, database in enumerate(databases, 1):
            print(f"\n[{i}/{len(databases)}] ", end="")
            pages_count = fetch_database(database, NOTION_DIR)
            total_pages_synced += pages_count
            databases_processed += 1
            time.sleep(1)  # Pause between databases
        
        # Step 2: Discover and sync root-level pages
        root_pages = discover_root_pages()
        
        if root_pages:
            print(f"\n{'='*60}")
            print(f"SYNCING {len(root_pages)} ROOT-LEVEL PAGES")
            print(f"{'='*60}\n")
            
            for i, page in enumerate(root_pages, 1):
                print(f"\n[{i}/{len(root_pages)}] ", end="")
                pages_count = fetch_root_page(page, NOTION_DIR)
                total_pages_synced += pages_count
                root_pages_processed += 1
                time.sleep(0.5)  # Pause between pages
        
        print("\n" + "="*60)
        print("✓ FULL SYNC COMPLETE!")
        print(f"  Databases processed: {databases_processed}")
        print(f"  Root pages processed: {root_pages_processed}")
        print(f"  Total pages synced: {total_pages_synced}")
        print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        update_status_after_full_sync(
            total_pages=total_pages_synced,
            databases_processed=databases_processed,
            root_pages_processed=root_pages_processed,
        )
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Partial results may have been saved.")
        print(f"  Progress: {databases_processed} databases, {root_pages_processed} root pages")
    except Exception as e:
        print(f"\nError during sync: {e}")
        import traceback
        traceback.print_exc()

def format_iso_timestamp(dt: datetime) -> str:
    """Format datetime as ISO string with a trailing Z."""
    return (
        dt.astimezone(timezone.utc)
        .replace(tzinfo=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def update_status_after_full_sync(
    total_pages: int,
    databases_processed: int,
    root_pages_processed: int,
) -> None:
    """Update the Notion status doc after a successful full sync."""
    if not STATUS_PATH.exists():
        print(f"Warning: status doc not found at {STATUS_PATH}, skipping status update.")
        return
    
    text = STATUS_PATH.read_text(encoding="utf-8")
    completed_at = datetime.now(timezone.utc)
    completed_ts = format_iso_timestamp(completed_at)
    
    # Update last full sync timestamp
    updated_text, replacements = re.subn(
        r"(`lastFullSyncTimestamp`:\s*)([0-9T:\-]+Z|None)",
        rf"\1{completed_ts}",
        text,
        count=1,
    )
    if replacements == 0:
        print("Warning: could not locate `lastFullSyncTimestamp` in status doc.")
        return
    text = updated_text
    
    # Update next full sync target if present
    next_full = (completed_at + timedelta(days=30)).strftime("%Y-%m-%d")
    text, _ = re.subn(
        r"(`nextFullSync`:\s*)([0-9T:\-]+|None)",
        rf"\1{next_full}",
        text,
        count=1,
    )
    
    lines = text.splitlines()
    summary_line = (
        f"- {completed_at.strftime('%Y-%m-%d')}: Full auto-discovery sync → "
        f"{total_pages} pages ({databases_processed} databases, {root_pages_processed} workspace roots)"
    )
    
    try:
        history_idx = lines.index("## Full Sync History")
    except ValueError:
        print("Warning: `## Full Sync History` section missing in status doc.")
        STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    
    insert_idx = history_idx + 1
    while insert_idx < len(lines) and lines[insert_idx].strip() == "":
        insert_idx += 1
    
    if insert_idx < len(lines) and lines[insert_idx].strip() == "_None yet_":
        lines[insert_idx] = summary_line
    else:
        lines.insert(insert_idx, summary_line)
    
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Status doc updated with full-sync timestamp.")


def main():
    """Main function to fetch Notion documents.
    
    Supports two modes:
    1. Auto-discovery mode (default): Discovers and syncs all databases and pages.
    2. Manual mode: Use --manual flag to use legacy stage-based fetching.
    """
    import sys
    
    if not NOTION_API_SECRET:
        print("Error: NOTION_API_SECRET environment variable not set")
        print("Please set it with: export NOTION_API_SECRET='your_secret_here'")
        return
    
    # Check for manual mode flag
    manual_mode = "--manual" in sys.argv or "-m" in sys.argv
    
    if manual_mode:
        # Legacy manual mode - stage-based fetching
        print("="*60)
        print("NOTION DOCUMENTS FETCHER - MANUAL MODE")
        print("="*60)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        try:
            # Stage 1: Wiki + CEO (set NOTION_WIKI_PAGE_ID or pass page_url to fetch_wiki)
            fetch_wiki()
            time.sleep(2)
            
            fetch_ceo_pages()
            time.sleep(2)
            
            # Stage 2: Product
            fetch_product_pages()
            time.sleep(2)
            
            # Stage 3: Operations + Success
            fetch_operations_pages()
            time.sleep(2)
            
            fetch_success_pages()
            
            print("\n" + "="*60)
            print("✓ ALL STAGES COMPLETE!")
            print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)
        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Partial results may have been saved.")
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
    else:
        # Auto-discovery mode - discover and sync everything
        sync_all_notion_content(auto_discover=True)

if __name__ == "__main__":
    main()

