# Serving layer (Postgres / Supabase)

## What this is

Today, the Streamlit candidate lookup app ([app/streamlit/dashboard.py](../app/streamlit/dashboard.py))
reads directly from `data/gold/*.csv`. That's fine for a three-candidate
prototype, but it doesn't scale to a real frontend with concurrent users,
auth, or a hosted backend.

This adds a **serving layer**: a small, well-defined set of Postgres tables
that a frontend could eventually read from instead of local files. It does
**not** change the Streamlit app — that keeps using the CSV fallback for
now (see [Streamlit stays on CSV for now](#streamlit-stays-on-csv-for-now)
below). This is purely additive infrastructure.

```
DuckDB marts (sql/marts/*.sql)  ─┐
                                  ├─► src/storage/export_to_postgres.py ─► Postgres / Supabase
data/gold/*.csv (fallback)      ─┘        (6 serving tables)
```

## The six serving tables

Defined in [sql/postgres/create_serving_tables.sql](../sql/postgres/create_serving_tables.sql):

| Table | What it holds | Upsert key |
|---|---|---|
| `candidate_profiles` | Core dossier fields: party, court, bar status, campaign finance snapshot, court context, SCJC result | `candidate_name` |
| `candidate_profile_completeness` | Data-completeness metrics for the tracked prototype fields (not a candidate-quality score) | `candidate_name` |
| `candidate_context_notes` | Interpretation/caveat notes ("OCA metrics are court-level context...") | `candidate_name, risk_type` |
| `source_quality` | Per-source rollup of how many context notes exist and how severe they are | `source_id` |
| `pipeline_runs` | One row per pipeline execution, parsed from `reports/pipeline_runs/run_*.txt` | `run_id` |
| `semantic_candidate_summaries` | Pre-generated plain-English paragraphs per candidate, built by deterministic templates (no LLM) | `candidate_name` |

`candidate_profile_completeness`, `candidate_context_notes`, and
`semantic_candidate_summaries` have a foreign key back to
`candidate_profiles.candidate_name`, so a candidate's profile row must
exist before its related rows can be written. `export_to_postgres.py`
always writes the tables in that dependency order.

All of the same neutrality rules that apply everywhere else in this
project apply here too: nothing in this schema ranks or scores candidates
against each other, "completeness" is a data-quality signal, and every
caveat (`source_caveat`, `candidate_context_notes.risk_message`) is
preserved rather than summarized away.

## Where the data comes from

`src/storage/export_to_postgres.py` prefers the DuckDB warehouse
(`data/warehouse/spartan_campaign.duckdb`, built by
`src/storage/build_duckdb.py` and `src/storage/run_sql_models.py`) when it
exists, and reads `sql/marts/mart_source_quality.sql` /
`sql/marts/mart_candidate_context.sql` output directly. If the warehouse
doesn't exist yet, it falls back to `data/gold/*.csv` and computes the
equivalent source-quality rollup in pandas. Either path produces the same
six DataFrames, and `filer_id` / `source_id` are always kept as text so
leading zeros survive.

`pipeline_runs` is the one exception: it's always parsed from
`reports/pipeline_runs/run_*.txt`, regardless of which data path is used,
since that's the only place run status/timestamp/error information lives.

## Running it locally

### 1. Preview without a database

```bash
python src/storage/export_to_postgres.py --dry-run
```

This builds all six tables in memory and prints row counts, columns, and a
sample row for each — no `DATABASE_URL`, no network connection, nothing
written anywhere. Use this to sanity-check the data before pointing it at
a real database.

### 2. Point it at a real Postgres database

Set `DATABASE_URL` to a standard Postgres connection string and run the
script with no flags:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/spartan_judicial"
python src/storage/export_to_postgres.py
```

The script will:

1. Apply `sql/postgres/create_serving_tables.sql` (every statement is
   `CREATE TABLE IF NOT EXISTS`, so this is safe to run every time — it
   never touches existing data).
2. Upsert each of the six tables via `INSERT ... ON CONFLICT DO UPDATE`, so
   re-running the export refreshes existing rows in place instead of
   duplicating them.

If `DATABASE_URL` is not set (and `--dry-run` wasn't passed), the script
logs a clear error and exits with a non-zero status instead of raising a
raw connection traceback:

```
DATABASE_URL is not set. Set it to your Postgres/Supabase connection string
(e.g. postgresql://user:password@host:5432/dbname), or re-run with --dry-run
to preview the export without a database. See docs/serving_layer.md.
```

### 3. Running Postgres locally (optional)

Any local Postgres works. For example, with Docker:

```bash
docker run --name spartan-postgres -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 -d postgres:16

export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"
python src/storage/export_to_postgres.py
```

No credentials are hardcoded anywhere in this repo — `DATABASE_URL` is the
only way the script learns how to connect, and it's never logged.

## How Supabase fits in

Supabase is hosted Postgres, so nothing about this design is
Supabase-specific — the same script and schema work unmodified. To use it:

1. Create a Supabase project and grab the connection string from
   **Project Settings → Database → Connection string** (use the "URI"
   format, e.g. `postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres`).
2. Either apply `sql/postgres/create_serving_tables.sql` yourself via the
   Supabase SQL editor, or just set `DATABASE_URL` to that connection
   string and run `export_to_postgres.py` — it applies the schema
   automatically.
3. Point a frontend at the same Supabase project using Supabase's
   auto-generated REST/JS client, reading straight from the six tables
   above.

Nothing in this repo depends on Supabase-specific features (RLS policies,
Supabase Auth, edge functions, etc.) — those would be added on the
Supabase side, on top of this plain Postgres schema, when the frontend
work actually starts.

## Streamlit stays on CSV for now

`app/streamlit/dashboard.py` is unchanged by this work and keeps reading
`data/gold/*.csv` directly. This serving layer is meant to be adopted
later, once there's an actual frontend (or a Streamlit rewrite) that wants
to read from a shared, hosted database instead of local files bundled with
the app. Standing up the Postgres tables now, without touching the
Streamlit app, lets that migration happen independently and lets the two
data paths be compared side by side in the meantime.

## Local setup

```bash
pip install -r requirements.txt   # includes sqlalchemy + psycopg2-binary
```

No `DATABASE_URL` is required for `--dry-run`, for the existing CSV/DuckDB
pipeline, or for CI — Postgres is entirely optional infrastructure at this
stage.
