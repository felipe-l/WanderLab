# WanderLab Agent Infrastructure

## What This Is
A weekly automated research pipeline with 4 agents on 4 Oracle Cloud ARM servers. Finds complaints about paid software, scores them, synthesizes opportunity briefs, delivers to Discord.

## Architecture
- **Monorepo** with `shared/` library and `agents/{scout,filter,analyst,supervisor}/`
- Agents coordinate via `pipeline_runs` table in Supabase
- LLM calls go through OpenRouter (OpenAI SDK with custom base URL)
- Scout + Filter use Haiku, Analyst uses Sonnet, Supervisor has no LLM

## Key Patterns
- `shared/` is a plain Python package — NOT pip-installed, rsynced to each box
- Each agent's `main.py` adds shared to sys.path via `sys.path.insert(0, ...)`
- `PipelineRunContext` context manager handles all status tracking
- All Supabase helpers are in `shared/supabase_client.py`
- Retry with exponential backoff on all external calls

## Running Locally
```bash
# From any agent directory:
cd agents/scout
pip install -r requirements.txt
# Set env vars (see .env.example)
python main.py
```

## Data Flow
Scout → pipeline_raw → Filter → pipeline_filtered → Analyst → pipeline_opportunities → Discord
