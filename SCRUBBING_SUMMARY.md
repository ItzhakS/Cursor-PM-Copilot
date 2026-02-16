# Scrubbing Complete - Ready for GitHub

All personal and company-specific information has been removed from the Scripts and Custom instructions folders.

## Summary of changes

### Scripts folder (`PM Copilot/Scripts/`)

**API Keys & Secrets (moved to environment variables)**
- `NOTION_API_SECRET` - now reads from env only
- `LINEAR_API_KEY` - now reads from env only

**Personal paths (genericized)**
- NDDF pricing script: `/Users/itzhak/Exponential Triage/...` → `NDDF_ROOT` env var (default: `./nddf_data`)

**Company-specific terms (removed)**
- "Triage Wiki" → "Wiki"
- "Referral Triage" → configurable via `LINEAR_TEAM_NAME` (default: "My Team")
- "Office of the CEO" → "Leadership"
- "Operations Sales" → "Operations"
- "Success Support" → "Customer Success"
- "Product Directory" → "Product"
- "TRIAGE-504" (in examples) → "ISSUE-504"
- Hardcoded Notion page/database IDs removed

**Output paths (configurable)**
- Notion: `NOTION_OUTPUT_DIR` (default: `output/Notion`)
- Linear: `LINEAR_OUTPUT_DIR` (default: `output/Linear`)

**New files added**
- `.env.example` - template for environment variables
- `README.md` - overview of all scripts and configuration
- `.gitignore` - ignores `.env` to prevent secret leaks

### Custom instructions folder (`PM Copilot/Custom instructions/`)

**Stakeholder names (genericized)**
- Adam, Daniel, Sam, Joel, Yoni, Chen, Yitzi, Mordechai, Jasmine, Roey → generic roles (engineering lead, CEO, CX team, data team, sales team, Chief of Staff, design/marketing team, operations, leadership)

**Company-specific terms (removed)**
- "Exponential" → "company"
- "Triage makes PACs more profitable" → "Our product makes [customers] more [valuable outcome]"
- "SNF admin, HHA intake" → "admins, end users, billing, operations"
- "Turbo Auth, reimbursement automation" → "new product areas or feature expansions"

**Internal processes (genericized)**
- "EVO planning" → "planning meetings"
- "EVOs remain internal-only" → "internal objectives remain internal-only"
- "@Initiative level context" → "initiative context" or "relevant project space"
- "@Meetings", "@Newsletters" → "designated folder", "initiative folder"

## Before publishing to GitHub

1. **Rotate the exposed secrets**
   - The old Notion and Linear API keys were hardcoded; treat them as compromised
   - Create new integration/API keys and only store them in your local `.env`

2. **Verify `.gitignore` includes `.env`**
   - The Scripts folder has its own `.gitignore` that ignores `.env`
   - Add `.env` to your root `.gitignore` as well if publishing the entire repo

3. **Optional: Add a root README**
   - Mention that scripts read config from environment variables
   - Direct users to copy `.env.example` to `.env` and fill in their keys
   - Note that `.env` should never be committed

## What's safe to publish

✅ All scripts with env-based configuration
✅ All Custom instructions playbooks (fully genericized)
✅ `.env.example` template
✅ README files
✅ `.gitignore` files

❌ Your actual `.env` file (should never be committed)
❌ Any existing output folders with real company data
