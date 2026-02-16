# Cursor PM Copilot

An AI-powered Product Manager workspace that provides strategic coaching, automated sync workflows, and structured action playbooks for product management at scale.

## What This Project Does

This repository configures Cursor IDE as an intelligent product management copilot that:

- **Provides strategic coaching**: Socratic-first guidance aligned with your company's goals, stakeholders, and operating rhythm
- **Automates data sync**: Use MCP servers for real-time integrations or Python scripts for scheduled syncing of Notion, Linear, and other tools
- **Offers structured playbooks**: Predefined workflows for product briefs, PMF assessment, research, roadmap planning, newsletters, and more
- **Maintains context**: Organized directories for company-level strategy, initiative tracking, and scratchpad work

## Project Structure

```
.
├── .cursor/rules/          # Cursor AI behavior rules (job context, coaching style, action playbooks)
├── PM Copilot/
│   ├── Company level context/    # Strategy docs, Notion pages, performance reviews
│   ├── Initiative level context/ # Active initiative plans and work logs
│   ├── Custom instructions/      # Action playbooks (Product Brief, PMF, Research, etc.)
│   ├── Rules/                    # Additional PM rules
│   ├── Scratchpad/               # Temporary workspace
│   └── Scripts/                  # Automation scripts for Notion, Linear, Other Integrations
└── README.md
```

## Quick Start

### 1. Clone the Repository

```bash
git clone <your-repo-url> cursor-pm-copilot
cd cursor-pm-copilot
```

### 2. Customize Cursor Rules

Edit the files in `.cursor/rules/` to match your context:

- **`job-context.mdc`**: Update with your role, company, stakeholders, KPIs, and operating rhythm
- **`ai-copilot-behavior.mdc`**: Adjust coaching style and interaction preferences
- **`action-playbooks.mdc`**: Review and customize action workflows

### 3. Set Up Integrations (Optional)

#### Option A: MCP Servers (Recommended)

**Model Context Protocol (MCP)** provides native, real-time integrations without writing code. Instead of syncing data with scripts, the AI can query tools directly during conversations.

**Benefits over API scripts:**
- No manual sync required—data is always current
- AI can read and write directly to external tools
- Simpler setup—just configure the MCP server
- More interactive—AI can respond to live changes

**Available MCP integrations:**
- **Notion MCP** — Query databases, read/write pages on-demand
- **Linear MCP** — Fetch issues, update statuses interactively
- **Byterover MCP** — Knowledge storage and retrieval
- **Browser MCP** — Test web apps, verify UI changes

**Setup:** Add MCP servers to your Cursor settings (see [Cursor MCP docs](https://docs.cursor.com/advanced/model-context-protocol)).

#### Option B: API Scripts (Legacy)

If you prefer static syncing or need offline access:

1. Install Python dependencies:
   ```bash
   pip install requests
   ```

2. Create a `.env` file with your API keys:
   ```bash
   # Notion
   NOTION_API_SECRET=your_notion_secret
   NOTION_OUTPUT_DIR=PM Copilot/Company level context/Notion
   
   # Linear
   LINEAR_API_KEY=your_linear_key
   LINEAR_TEAM_NAME=Your Team Name
   LINEAR_OUTPUT_DIR=PM Copilot/Company level context/Linear
   ```

3. Run sync scripts as needed:
   ```bash
   # Full Notion sync
   python "PM Copilot/Scripts/fetch_notion_docs.py"
   
   # Incremental Notion updates
   python "PM Copilot/Scripts/fetch_notion_incremental_updates.py"
   
   # Linear tasks sync
   python "PM Copilot/Scripts/fetch_and_replace_all_linear_tasks.py"
   ```

See `PM Copilot/Scripts/README.md` for detailed script documentation.

### 4. Open in Cursor

1. Open this folder in Cursor IDE
2. The AI will automatically load the rules from `.cursor/rules/`
3. Start a conversation—reference files with `@` (e.g., `@Custom instructions/Action_Product_Brief.md`)

## How to Use

### Strategic Coaching
Ask the copilot for guidance on prioritization, stakeholder management, or product decisions. It will:
- Ask clarifying questions before advising
- Anchor recommendations to your strategic pillars
- Surface dependencies and risks proactively

### Action Playbooks
Reference playbooks in `@Custom instructions/` for structured workflows:
- `Action_Product_Brief.md` — Spec new features or products
- `Action_PMF.md` — Assess product-market fit
- `Action_Research.md` — Run discovery or validation research
- `Action_Roadmap_Planning.md` — Build or refresh roadmaps
- `Action_Meeting_Summary.md` — Summarize meetings or interviews
- `Action_Notion_Sync.md` / `Action_Linear_Sync.md` — Sync external data

### Knowledge Management
- Store company strategy, meeting notes, and retrospectives in `Company level context/`
- Track active initiatives in `Initiative level context/`
- Use `Scratchpad/` for temporary work

## Customization Tips

1. **Tailor the job context**: Update stakeholder names, strategic goals, and meeting cadences in `.cursor/rules/job-context.mdc`
2. **Adjust coaching style**: Modify tone, challenge level, and interaction patterns in `.cursor/rules/ai-copilot-behavior.mdc`
3. **Extend playbooks**: Add new action types in `Custom instructions/` and reference them in `action-playbooks.mdc`
4. **Integrate tools**: Use MCP servers for live integrations, or add API scripts for other data sources (Jira, GitHub, Confluence) in `Scripts/`

## Requirements

- **Cursor IDE** (download from [cursor.sh](https://cursor.sh))
- **Python 3** (for sync scripts)
- **API keys** (Notion, Linear) if using automation

## Security Notes

- Never commit `.env` files (already in `.gitignore`)
- Review Cursor rules before sharing the repo—they may contain sensitive company context
- Notion/Linear data synced locally may include confidential information

## Contributing

This is a personal workspace template. Fork and customize for your own use. Consider:
- Anonymizing company-specific details before sharing publicly
- Creating generic versions of rules and playbooks for reuse
- Sharing useful scripts or playbook patterns with the community

## License

Customize this section based on your needs (e.g., MIT, private use only, etc.)

---

**Built for product leaders who want AI that understands their context, challenges their thinking, and accelerates execution.**
