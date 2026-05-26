# AutismGPT Lesson Creation Agent

A human-in-the-loop Python MVP for designing structured AutismGPT lessons — from a rough idea to a fully reviewed content package in one guided workflow.

## Final Outputs

| File | Description |
|---|---|
| `system_prompt.md` | The approved Nessa system prompt for the lesson |
| `<lesson_id>_package.xlsx` | Excel workbook with 4 structured sheets |

### Excel Sheets

| Sheet | Contents |
|---|---|
| **Session Script** | Full dialog between Nessa and Child, intro + all rounds |
| **Practice Scenarios** | Scenario prompts, hints, target responses, difficulty |
| **Scenario Image** | Image generation prompts, style, key elements |
| **QA Review** | Per-category check results with pass/fail/warning status |

---

## Workflow

```
User: describes lesson idea
  └─ Step 1: Session Script (dialog format)     ← draft → feedback → approve
     └─ Step 2: Prompt Library Search            ← auto-searches saved prompts
        └─ Step 3: System Prompt                 ← draft → feedback → approve
           └─ Step 4: Practice Scenarios + Images
              └─ Step 5: Export (.xlsx + .md)
                 └─ Step 6: QA Review
```

---

## Setup

### 1. Install dependencies

```bash
cd autism_gpt_mvp
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key:
# ANTHROPIC_API_KEY=sk-ant-...
```

---

## Streamlit Web Interface (recommended)

```bash
cd autism_gpt_mvp
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

**API key:** If `ANTHROPIC_API_KEY` is not set in `.env`, paste it directly into the sidebar when the app opens.

---

## Navigating Steps

The app tracks which steps are complete. You can freely **go back** to any completed step using the sidebar — your approved content is preserved. Revising an earlier step marks all downstream steps as stale (⚠️) so you know they may need updating, but their content is not deleted.

| Sidebar indicator | Meaning |
|---|---|
| ✅ Step name | Approved and up to date |
| ⚠️ Step name | Previously approved, but an earlier step was revised |
| _(no indicator)_ | Not yet completed |

After approving a step, the app automatically advances to the next one. You can also jump back at any time by clicking a completed step in the sidebar.

---

## Prompt Library

### How it's stored

The prompt library is a persistent JSON file at:

```
data/prompt_library/prompts.json
```

This file is read from disk on every access — no in-memory cache. It starts empty (`[]`) and grows as you add prompts through the Library Manager. Each entry has:

| Field | Description |
|---|---|
| `id` | Auto-generated UUID |
| `title` | Short display name |
| `objective_type` | e.g. "Social Communication" |
| `skill_type` | e.g. "Greeting", "Emotion Recognition" |
| `tags` | List of searchable keywords |
| `notes` | Internal notes (not sent to LLM) |
| `system_prompt` | Full system prompt text |
| `created_at` / `updated_at` | ISO timestamps |

When the library is empty, the app falls back to `autism_gpt/prompt_library/sample_prompts.json` and clearly labels results as **"(fallback sample)"** so you know they are not from your saved prompts.

---

### Adding one prompt

1. Click **📚 Prompt Library** in the sidebar to open the Library Manager.
2. Go to the **➕ Add Prompt** tab.
3. Fill in the form: Title, Objective Type, Skill Type, Tags (comma-separated), Notes, and the full System Prompt text.
4. Click **Save Prompt**.

The prompt is immediately written to `data/prompt_library/prompts.json` and available for retrieval in future sessions.

---

### Bulk-adding multiple prompts

1. Open **📚 Prompt Library** → **📦 Bulk Add** tab.
2. Paste a JSON array of prompt objects. Each object must have at least `title` and `system_prompt`. All other fields are optional.

Example format:

```json
[
  {
    "title": "Word Mystery — Animals",
    "objective_type": "Vocabulary",
    "skill_type": "Word Recognition",
    "tags": ["animals", "vocabulary", "beginner"],
    "notes": "Used in pilot session, worked well.",
    "system_prompt": "You are Nessa, a friendly AI tutor..."
  },
  {
    "title": "Greeting Practice",
    "skill_type": "Social Communication",
    "tags": ["greetings", "social"],
    "system_prompt": "You are Nessa..."
  }
]
```

3. Click **Parse JSON** to preview the entries.
4. Click **Import N Prompts** to save them all.

---

### How Step 2 uses saved prompts (reference only)

When the app reaches Step 2 (Prompt Library Search), it automatically searches your saved prompts using keyword overlap against the current lesson's skill type, activity format, and title.

**Saved prompts are used as structural references only — never as content to copy.** The system prompt generation template instructs the LLM to:

| Extract (reusable across any lesson) | Do NOT copy (objective-specific) |
|---|---|
| Overall prompt section structure | Skills or topics from the old lesson |
| Tool call patterns (`get_scenario()`, `evaluate()`, `show_rewards()`) | Scenario content or target words |
| Nessa's language rules (sentence length, tone) | Teaching steps that don't fit this lesson's format |
| Hint sequencing (small hint → big hint → reveal) | Any phrasing tied to the old lesson's subject |
| Praise formulas, safety rules, formatting conventions | — |

This means the generated system prompt always reflects the **current lesson's topic**, using saved prompts only as a style and structure scaffold.

---

## Prompt Library Manager

Access via **📚 Prompt Library** in the sidebar. Three tabs:

| Tab | What you can do |
|---|---|
| **📋 All Prompts** | View all saved prompts, expand to read full text, edit metadata, delete |
| **➕ Add Prompt** | Add a single prompt with a form |
| **📦 Bulk Add** | Paste a JSON array to import multiple prompts at once |

---

## Project Structure

```
autism_gpt_mvp/
├── app.py                               # Streamlit UI (main entry point)
├── main.py                              # CLI entry point
├── requirements.txt
├── .env.example
├── data/
│   └── prompt_library/
│       └── prompts.json                 # Persistent prompt library (JSON)
├── autism_gpt/
│   ├── agent.py                         # CLI orchestrator
│   ├── schemas.py                       # Pydantic models
│   ├── llm.py                           # Anthropic API wrapper
│   ├── library_db.py                    # PromptLibraryDB — CRUD + search
│   ├── steps/
│   │   ├── lesson_flow.py               # Step 1: session script draft + revise
│   │   ├── prompt_library.py            # Step 2: search saved prompts
│   │   ├── system_prompt.py             # Step 3: system prompt draft + revise
│   │   ├── scenarios.py                 # Step 4: scenarios + image prompts
│   │   └── qa_review.py                 # Step 6: QA checklist
│   ├── exporters/
│   │   ├── excel.py                     # Export to .xlsx (export_bytes for web)
│   │   └── markdown.py                  # Export system_prompt.md
│   └── prompt_library/
│       └── sample_prompts.json          # Fallback samples (used when DB is empty)
└── templates/
    ├── agent_system.txt
    ├── lesson_flow_draft.txt
    ├── lesson_flow_revise.txt
    ├── system_prompt_create.txt
    ├── system_prompt_revise.txt
    ├── scenario_create.txt
    ├── image_create.txt
    └── qa_review.txt
```

---

## Key Design Decisions

### Topic-agnostic lesson format
The LLM identifies the appropriate activity format (Question Practice, Word Mystery Game, Emotion Detective, etc.) based on the lesson idea — it does NOT default to vocabulary for every topic. The `lesson_flow_draft.txt` template includes explicit guard rules and non-vocabulary examples.

### Human-in-the-loop at every creative step
Steps 1 and 3 run a revision loop: the agent drafts, the user reads the output, gives free-text feedback, and the agent revises — until approved.

### Persistent JSON prompt library
`PromptLibraryDB` reads from `data/prompt_library/prompts.json` on every call (no stale in-memory state). When the library is empty, falls back to `sample_prompts.json` with clear labeling.

### Prompt caching
The agent system template (`agent_system.txt`) is sent as an Anthropic ephemeral cache block, reducing token cost on repeated calls within a session.

### Structured JSON outputs
All structured data (session script, scenarios, images, QA) is requested as JSON and parsed into Pydantic models.

---

## Models Used

- **claude-sonnet-4-6** — all LLM calls (drafting, revision, QA)
- Prompt caching enabled on the agent system prompt for cost efficiency
