# Open Questions

## For Chris

- Should the dashboard be primarily internal-facing for Spartan or eventually voter-facing?
- Should the first dashboard prioritize candidate profiles, campaign readiness, or source verification?
- Are the three target campaigns still the correct scope for the final deliverable?
- Are there internal campaign data sources we should include later, such as donor lists, CRM exports, call-time logs, or event records?
- What should the final August presentation emphasize: technical architecture, business usefulness, or campaign readiness?

## For Ayesha / Team

- Which source links need manual cleanup?
- Which fields are confusing or need a better data dictionary definition?
- Which source caveats should be visible in the dashboard?
- What should the source inventory include beyond the current public sources?

## Technical Questions

- Should the MVP use DuckDB or Postgres/Supabase?
- Should orchestration be Prefect or Dagster-lite?
- Should the first dashboard be Streamlit?
- Should validation use Pydantic only first, or also Great Expectations/Soda later?
