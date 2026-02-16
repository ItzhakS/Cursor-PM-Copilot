# Notion Fetch & Sync Plan

Draft sync status doc

- Refresh `PM Copilot/Company level context/Notion/SYNC_STATUS.md` to track Notion full-sync and incremental cadence with `lastFullSyncTimestamp`, `lastIncrementalSyncTimestamp`, and `nextFullSync` fields.
- Document how to bump timestamps after monthly full runs and daily incremental runs.

Implement dual-script workflow

- Keep `PM Copilot/Scripts/fetch_notion_docs.py` focused on the monthly full auto-discovery sync and ensure it records its completion timestamp in the status doc.
- Add `PM Copilot/Scripts/fetch_notion_incremental_updates.py` to load the incremental timestamp, pull Notion pages/databases edited since then, sync the affected markdown files, and persist the updated marker plus a summary entry.

Document run workflow

- Update the Notion scripts README with commands and guidance for the monthly full sync vs daily incremental sync routines.


