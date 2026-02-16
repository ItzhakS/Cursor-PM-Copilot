# Notion Sync Status
- `lastIncrementalSyncTimestamp`: 2025-12-07T14:34:06Z

## Daily Incremental Sync

- Run `python3 "PM Copilot/Scripts/fetch_notion_incremental_updates.py"` each weekday (or after major edits).
- The script reads `lastIncrementalSyncTimestamp`, exports changed pages, and updates the timestamp plus **Incremental Summaries** automatically.
- If a run finds no changes, still commit the updated timestamp so we can prove the check happened.

## Monthly Full Sync

- Run `python3 "PM Copilot/Scripts/fetch_notion_docs.py"` (auto-discovery mode) at least once per month or when onboarding new databases.
- After completion, confirm `lastFullSyncTimestamp` and `nextFullSync` above, and review the entry added under **Full Sync History**.
- Use the `--manual` flag only for legacy stage-based pulls; the auto-discovery path should be the default.

## Incremental Summaries



## Full Sync History



## Output Structure



## Reference Notes

- The full-sync script discovers databases and workspace pages automatically, batching requests to respect rate limits.
- Incremental syncs overwrite existing markdown files (no suffixes) so downstream RAG jobs always read the freshest copy.
- Each script logs progress to stdout; capture output when running unattended (cron, GitHub Actions).

