# Open Questions

## For Chris

1. Should the dashboard be primarily internal-facing for Spartan or eventually voter-facing?
2. Should the first dashboard prioritize candidate profiles, campaign readiness, or source verification?
3. Are the three target campaigns still the correct scope for the final deliverable?
4. Are there internal campaign data sources we should include later, such as donor lists, CRM exports, call-time logs, or event records?
5. What should the final August presentation emphasize: technical architecture, business usefulness, or campaign readiness?

## For Ayesha / Team

1. Which source links need manual cleanup?
2. Which fields are confusing or need a better data dictionary definition?
3. Which source caveats should be visible in the dashboard?
4. What should the source inventory include beyond the current public sources?

## Technical Questions

1. Should the MVP use DuckDB or Postgres/Supabase?
2. Should orchestration be Prefect or Dagster-lite?
3. Should the first dashboard be Streamlit?
4. Should validation use Pydantic only first, or also Great Expectations/Soda later?
