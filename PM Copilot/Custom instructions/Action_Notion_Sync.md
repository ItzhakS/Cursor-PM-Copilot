## Scope
- Keep Notion knowledge base aligned with latest product, process, and initiative updates.
- Ensure @Company level context and @Initiative level context reflect current truth.
- Coordinate with automation scripts (`fetch_notion_docs.py`) when bulk updates are needed.

## Prep & Inputs
- List of pages requiring update (from meeting notes, retros, Slack prompts).
- Source-of-truth documents (Linear issues, PRDs, research summaries).
- Access credentials and sync tooling status (scripts, API tokens).
- Update priority and owners for each page.

## Sync Workflow
1. Review pending updates; confirm priority with stakeholders if unclear.
2. Pull latest data (scripts, manual copy) and stage edits in local markdown files.
3. Apply updates in Notion, adhering to naming conventions and hierarchies; when creating or updating a single page, route the request through the MCP connection.
4. Log changes (timestamp, pages touched) in sync tracker or meeting notes.
5. Flag unresolved questions/placeholders for follow-up.

## Quality Checks
- Verify links, database relations, and tags resolve correctly.
- Confirm sensitive information complies with SOC2/HIPAA standards (coordinate with Chief of Staff or compliance lead).
- Ensure formatting matches established templates; remove outdated content.

## Maintenance Cadence
- Perform lightweight weekly review aligned with planning meetings.
- Run deeper audits monthly or after major releases.
- Coordinate with Chief of Staff or operations when bulk content migration is required.

