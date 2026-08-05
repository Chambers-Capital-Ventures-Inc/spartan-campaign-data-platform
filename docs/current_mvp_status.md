# Current MVP Status

## What works

- Candidate lookup prototype runs locally.
- Raw target-three dossier is preserved.
- Silver cleaned dossier is generated.
- Pydantic validation passes.
- Gold candidate dossier outputs are generated.
- Profile completeness and interpretation notes are generated.
- One-command runner exists with run_id logging.
- Streamlit lookup prototype works for three target campaigns.

## What this proves

The project can turn a manually assembled target-campaign dossier into validated, source-linked candidate profile outputs.

## What this does not yet include

- Parquet lake storage
- DuckDB warehouse
- SQL/dbt-style models
- Dagster orchestration
- PostgreSQL/Supabase serving layer
- LLM-generated semantic summaries
- full source refresh automation
- full data versioning
- production deployment