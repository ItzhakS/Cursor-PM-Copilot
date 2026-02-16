# Scripts

Automation for syncing Notion, Linear, and optional NDDF pricing data. All secrets and paths are configured via environment variables so the repo can be used generically.

## Quick setup

1. Copy `.env.example` to `.env` and fill in your API keys.
2. Do **not** commit `.env` (add it to `.gitignore` if publishing).

## Environment variables

| Variable | Used by | Description |
|----------|---------|-------------|
| `NOTION_API_SECRET` | Notion scripts | Required. From [Notion integrations](https://www.notion.so/my-integrations). |
| `NOTION_OUTPUT_DIR` | Notion scripts | Optional. Where markdown is written (default: repo root `output/Notion`). |
| `NOTION_WIKI_PAGE_ID` | `fetch_notion_docs.py --manual` | Optional. Wiki page/database ID for manual mode. |
| `NOTION_PRODUCT_DATABASE_ID` | `fetch_notion_docs.py --manual` | Optional. Product database ID for manual mode. |
| `LINEAR_API_KEY` | Linear scripts | Required. From [Linear API](https://linear.app/settings/api). |
| `LINEAR_TEAM_NAME` | Linear scripts | Optional. Team name in Linear (default: `My Team`). |
| `LINEAR_BATCH_PREFIX` | Linear scripts | Optional. Batch file prefix (default: `Issues-Batch`). |
| `LINEAR_OUTPUT_DIR` | Linear scripts | Optional. Where batch markdown and status are written (default: repo root `output/Linear`). |
| `NDDF_ROOT` | `extract_nddf_pricing.py` | Optional. Path to NDDF Plus "Descriptive and Pricing" data directory (default: `./nddf_data`). |
| `NOTION_BASE_DIR` | `compare_notion_local.py` | Optional. Base dir for local Notion files (default: `output/Notion`). |

## Scripts

- **Notion**: `fetch_notion_docs.py` (full sync), `fetch_notion_incremental_updates.py` (incremental), `compare_notion_local.py` (compare local vs Notion). See `README_NOTION.md`.
- **Linear**: `fetch_and_replace_all_linear_tasks.py` (full fetch), `fetch_linear_updates_since_last_sync.py` (incremental).
- **NDDF**: `extract_nddf_pricing.py` — extracts pricing from NDDF Plus flat files (set `NDDF_ROOT`).

## Requirements

- Python 3
- `requests` for Notion and Linear scripts
