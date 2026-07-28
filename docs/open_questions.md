# Open Questions

## For Chris

### Project Scope

- Should the dashboard be primarily internal-facing for Spartan or eventually voter-facing?
- Should the first dashboard prioritize candidate profiles, campaign readiness, or source verification?
- Are the three target campaigns still the correct scope for the final deliverable?
- Are there internal campaign data sources we should include later, such as donor lists, CRM exports, call-time logs, or event records?
- What should the final August presentation emphasize: technical architecture, business usefulness, or campaign readiness?

### Source Inventory

- What does the **owner** field represent? The person maintaining the source, the original data provider, or the team member responsible for verification?
- What does **candidates_supported** represent? Should it list the target candidates searched or only candidates with data returned by the source?
- Does **spartan_engine_supported** indicate current implementation or planned future support?
- Does **manual_or_automated** describe the current verification process or the intended production pipeline?
- Should **source_url** point to the authoritative homepage or the exact page used during verification?
- Should verification_status use standardized values (e.g., Verified, Pending, Partial)?

---

## For Ayesha / Team

### Source Review

- Several source URLs could be made more specific by linking directly to the relevant search or dataset rather than the organization's homepage.
- Candidate identities should be manually verified across multiple sources to avoid matching the wrong individual when names are similar.
- Attorney profile information from the State Bar is partially self-reported and should be cross-checked when official verification is required.
- The SCJC archive only contains public disciplinary actions; absence from the archive does not necessarily indicate that no complaint or investigation exists.

### Data Dictionary

The following fields could benefit from clearer definitions:

- owner
- candidates_supported
- spartan_engine_supported
- manual_or_automated
- priority
- verification_status

### Dashboard

- Which source caveats should be surfaced directly in the dashboard versus remaining internal documentation?
- Should source freshness or last verification date be displayed to users?

---

## Technical Questions

- Should the MVP use DuckDB or Postgres/Supabase?
- Should orchestration be Prefect or Dagster-lite?
- Should the first dashboard be Streamlit?
- Should validation use Pydantic only first, or also Great Expectations/Soda later?
