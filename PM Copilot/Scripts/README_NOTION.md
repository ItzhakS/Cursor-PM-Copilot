# Notion Sync Scripts

Two companion scripts keep a local Notion export in sync (e.g. for RAG or docs).

## Setup

1. Create a Notion integration and copy the secret from https://www.notion.so/my-integrations.
2. Set the token before running either script:
   ```bash
   export NOTION_API_SECRET="your_secret_here"
   ```
   Or copy `.env.example` to `.env` and source it.

3. Optional: set `NOTION_OUTPUT_DIR` to choose where markdown is written (default: `output/Notion` under repo root).

## Monthly Full Sync

- Command: `python3 fetch_notion_docs.py`
- Discovers every accessible database and workspace page, then exports all content to markdown under the output directory.
- Updates `SYNC_STATUS.md` with `lastFullSyncTimestamp`, rolls `nextFullSync`, and appends an entry to **Full Sync History**.
- The optional `--manual` flag uses a stage-by-stage flow; set `NOTION_WIKI_PAGE_ID` and `NOTION_PRODUCT_DATABASE_ID` if you use manual mode.

## Daily Incremental Sync

- Command: `python3 fetch_notion_incremental_updates.py`
- Reads `lastIncrementalSyncTimestamp` from `SYNC_STATUS.md`, pulls only pages touched since that timestamp, and overwrites the affected markdown files in place.
- Updates the status doc with the new timestamp and prepends a concise summary line under **Incremental Summaries**.
- Safe to run multiple times per day; the timestamp always moves forward to reflect the last completed check.

## Behaviour & Notes

- Both scripts respect Notion rate limits with short sleeps between paginated calls.
- Markdown exports include page metadata (title, URL, created/edited dates) to simplify downstream diff reviews.
- Duplicate page titles are resolved via filename sanitisation; incremental runs search for the page ID to avoid accidental duplicates.
- Capture stdout/stderr when scheduling automated runs so we can trace failures quickly.

