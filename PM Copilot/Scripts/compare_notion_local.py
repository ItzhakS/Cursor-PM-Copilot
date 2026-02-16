#!/usr/bin/env python3
"""
Compare local Notion files with what's actually in Notion workspace
Identifies missing pages/databases and provides a detailed report
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set
from collections import defaultdict

# Import functions from fetch_notion_docs
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_notion_docs import (
    make_api_request, 
    format_page_id_with_dashes,
    extract_page_id_from_url,
    get_page_title,
    extract_text_from_rich_text,
    query_database,
    get_all_child_pages,
    get_page_blocks
)

# Configuration: uses NOTION_API_SECRET from fetch_notion_docs (env); override base dir with NOTION_BASE_DIR
NOTION_API_SECRET = os.environ.get("NOTION_API_SECRET", "")
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_BASE_DIR = Path(os.environ.get("NOTION_BASE_DIR", "output/Notion"))

# Headers for Notion API (must match fetch_notion_docs when using shared secret)
headers = {
    "Authorization": f"Bearer {NOTION_API_SECRET}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_all_accessible_pages():
    """Get all pages accessible to the integration"""
    print("Searching for all accessible pages in Notion...")
    
    all_pages = []
    has_more = True
    start_cursor = None
    
    while has_more:
        data = {
            "filter": {
                "value": "page",
                "property": "object"
            },
            "page_size": 100,
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
            all_pages.extend(batch_results)
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
            print(f"  Found {len(all_pages)} pages so far...")
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"Error searching: {e}")
            break
    
    print(f"Total accessible pages: {len(all_pages)}")
    return all_pages

def get_all_accessible_databases():
    """Get all databases accessible to the integration"""
    print("Searching for all accessible databases in Notion...")
    
    all_databases = []
    has_more = True
    start_cursor = None
    
    while has_more:
        data = {
            "filter": {
                "value": "database",
                "property": "object"
            },
            "page_size": 100,
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
            all_databases.extend(batch_results)
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
            print(f"  Found {len(all_databases)} databases so far...")
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"Error searching databases: {e}")
            break
    
    print(f"Total accessible databases: {len(all_databases)}")
    return all_databases

def get_database_title(database: Dict) -> str:
    """Extract database title"""
    title_array = database.get("title", [])
    if title_array:
        return extract_text_from_rich_text(title_array)
    return "Untitled Database"

def get_local_files():
    """Get all local markdown files and their metadata"""
    local_files = {}
    notion_dir = Path(NOTION_BASE_DIR)
    
    if not notion_dir.exists():
        print(f"Local Notion directory not found: {notion_dir}")
        return local_files
    
    # Walk through all subdirectories
    for root, dirs, files in os.walk(notion_dir):
        for file in files:
            if file.endswith('.md'):
                filepath = Path(root) / file
                relative_path = filepath.relative_to(notion_dir)
                
                # Try to extract Notion URL from file
                notion_url = None
                page_id = None
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Look for Notion URL in header
                        url_match = re.search(r'\*\*Notion URL:\*\* (.+)', content)
                        if url_match:
                            notion_url = url_match.group(1).strip()
                            page_id = extract_page_id_from_url(notion_url)
                except Exception as e:
                    pass
                
                local_files[filepath] = {
                    'relative_path': str(relative_path),
                    'filename': file,
                    'notion_url': notion_url,
                    'page_id': page_id,
                    'size': filepath.stat().st_size
                }
    
    return local_files

def extract_page_id_from_notion_url(url: str) -> str:
    """Extract page ID from Notion URL"""
    if not url:
        return None
    
    # Remove query parameters
    if "?" in url:
        url = url.split("?")[0]
    
    # Extract ID part
    url = url.replace("https://www.notion.so/", "").replace("https://notion.so/", "")
    # Remove dashes
    page_id = url.replace("-", "")
    
    if len(page_id) == 32:
        return page_id
    
    return None

def build_notion_page_map(pages: List[Dict], databases: List[Dict]) -> Dict:
    """Build a map of Notion pages by ID and by title"""
    page_map = {}
    title_map = defaultdict(list)
    
    # Process regular pages
    for page in pages:
        page_id = page.get("id", "").replace("-", "")
        title = get_page_title(page)
        url = page.get("url", "")
        parent = page.get("parent", {})
        
        page_map[page_id] = {
            'type': 'page',
            'title': title,
            'url': url,
            'parent': parent,
            'page_data': page
        }
        title_map[title.lower()].append(page_id)
    
    # Process databases
    for database in databases:
        db_id = database.get("id", "").replace("-", "")
        title = get_database_title(database)
        url = database.get("url", "")
        parent = database.get("parent", {})
        
        page_map[db_id] = {
            'type': 'database',
            'title': title,
            'url': url,
            'parent': parent,
            'page_data': database
        }
        title_map[title.lower()].append(db_id)
    
    return page_map, title_map

def find_missing_pages(notion_pages: Dict, local_files: Dict) -> Dict:
    """Compare Notion pages with local files to find missing ones"""
    missing = {
        'pages': [],
        'databases': [],
        'by_category': defaultdict(list)
    }
    
    # Build set of local page IDs
    local_page_ids = set()
    local_urls = set()
    
    for filepath, file_info in local_files.items():
        if file_info['page_id']:
            local_page_ids.add(file_info['page_id'].replace("-", ""))
        if file_info['notion_url']:
            local_urls.add(file_info['notion_url'])
    
    # Check each Notion page
    for page_id, page_info in notion_pages.items():
        clean_id = page_id.replace("-", "")
        
        if clean_id not in local_page_ids:
            # Check if URL matches
            if page_info['url'] not in local_urls:
                missing_item = {
                    'id': page_id,
                    'title': page_info['title'],
                    'url': page_info['url'],
                    'type': page_info['type']
                }
                
                if page_info['type'] == 'database':
                    missing['databases'].append(missing_item)
                else:
                    missing['pages'].append(missing_item)
                
                # Categorize by parent or title
                parent = page_info.get('parent', {})
                parent_type = parent.get('type', '')
                
                if parent_type == 'workspace':
                    missing['by_category']['Root Level'].append(missing_item)
                elif parent_type == 'page_id':
                    missing['by_category']['Child Pages'].append(missing_item)
                elif parent_type == 'database_id':
                    missing['by_category']['Database Entries'].append(missing_item)
                else:
                    missing['by_category']['Other'].append(missing_item)
    
    return missing

def analyze_database_contents(database_id: str) -> Dict:
    """Analyze a database to see how many pages it contains"""
    try:
        db_id_formatted = format_page_id_with_dashes(database_id.replace("-", ""))
        pages = query_database(db_id_formatted)
        return {
            'page_count': len(pages),
            'pages': pages
        }
    except Exception as e:
        return {
            'page_count': 0,
            'error': str(e)
        }

def generate_comparison_report(notion_pages: Dict, local_files: Dict, missing: Dict) -> str:
    """Generate a detailed comparison report"""
    report = []
    report.append("=" * 80)
    report.append("NOTION LOCAL COMPARISON REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Summary
    report.append("SUMMARY")
    report.append("-" * 80)
    report.append(f"Total Notion pages/databases: {len(notion_pages)}")
    report.append(f"Total local files: {len(local_files)}")
    report.append(f"Missing pages: {len(missing['pages'])}")
    report.append(f"Missing databases: {len(missing['databases'])}")
    report.append("")
    
    # Local files breakdown
    report.append("LOCAL FILES BREAKDOWN")
    report.append("-" * 80)
    by_directory = defaultdict(int)
    for filepath, info in local_files.items():
        dir_path = Path(info['relative_path']).parent
        by_directory[str(dir_path)] += 1
    
    for directory, count in sorted(by_directory.items()):
        report.append(f"  {directory}: {count} files")
    report.append("")
    
    # Missing databases
    if missing['databases']:
        report.append("MISSING DATABASES")
        report.append("-" * 80)
        for db in missing['databases']:
            report.append(f"  - {db['title']}")
            report.append(f"    URL: {db['url']}")
            report.append(f"    ID: {db['id']}")
            
            # Try to get page count
            analysis = analyze_database_contents(db['id'])
            if 'error' not in analysis:
                report.append(f"    Contains: {analysis['page_count']} pages")
            report.append("")
    
    # Missing pages by category
    if missing['pages'] or missing['databases']:
        report.append("MISSING PAGES BY CATEGORY")
        report.append("-" * 80)
        
        for category, items in missing['by_category'].items():
            if items:
                report.append(f"\n{category} ({len(items)} items):")
                for item in items[:20]:  # Limit to first 20 per category
                    report.append(f"  - {item['title']}")
                    report.append(f"    URL: {item['url']}")
                
                if len(items) > 20:
                    report.append(f"    ... and {len(items) - 20} more")
                report.append("")
        
        # All missing items (full list)
        report.append("\nFULL LIST OF MISSING ITEMS")
        report.append("-" * 80)
        report.append("\nDatabases:")
        for db in missing['databases']:
            report.append(f"  {db['title']} | {db['url']}")
        
        report.append("\nPages:")
        for page in missing['pages'][:100]:  # Limit to first 100
            report.append(f"  {page['title']} | {page['url']}")
        
        if len(missing['pages']) > 100:
            report.append(f"\n  ... and {len(missing['pages']) - 100} more pages")
    
    else:
        report.append("\n✓ NO MISSING PAGES - All Notion content is synced locally!")
    
    return "\n".join(report)

def main():
    """Main comparison function"""
    print("=" * 80)
    print("NOTION LOCAL COMPARISON TOOL")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Step 1: Get all Notion pages and databases
    print("\n[1/4] Fetching Notion pages and databases...")
    notion_pages_list = get_all_accessible_pages()
    notion_databases_list = get_all_accessible_databases()
    
    # Step 2: Build page map
    print("\n[2/4] Building Notion page map...")
    notion_page_map, notion_title_map = build_notion_page_map(notion_pages_list, notion_databases_list)
    print(f"  Found {len(notion_page_map)} total Notion items")
    
    # Step 3: Get local files
    print("\n[3/4] Scanning local files...")
    local_files = get_local_files()
    print(f"  Found {len(local_files)} local markdown files")
    
    # Step 4: Compare
    print("\n[4/4] Comparing Notion vs Local...")
    missing = find_missing_pages(notion_page_map, local_files)
    
    # Step 5: Generate report
    print("\nGenerating comparison report...")
    report = generate_comparison_report(notion_page_map, local_files, missing)
    
    # Save report
    report_path = NOTION_BASE_DIR / "comparison_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("\n" + "=" * 80)
    print("COMPARISON COMPLETE!")
    print("=" * 80)
    print(f"\nReport saved to: {report_path}")
    print("\n" + report)
    
    # Also save as JSON for programmatic access
    json_report = {
        'timestamp': datetime.now().isoformat(),
        'notion_count': len(notion_page_map),
        'local_count': len(local_files),
        'missing_pages': missing['pages'],
        'missing_databases': missing['databases'],
        'missing_by_category': {k: [item['title'] for item in v] for k, v in missing['by_category'].items()}
    }
    
    json_path = NOTION_BASE_DIR / "comparison_report.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    
    print(f"\nJSON report saved to: {json_path}")

if __name__ == "__main__":
    main()

