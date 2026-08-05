"""
Spartan Judicial Campaign Data Platform — Streamlit dashboard.

This is a read-only prototype dashboard for a non-technical stakeholder demo.
It renders the gold-layer outputs of the bronze -> silver -> gold pipeline
(candidate dossiers, data-readiness scores, and risk signals) alongside the
validation reports that confirm those outputs match their expected schema.

Scope / framing (do not violate when editing):
- This dashboard describes DATA COMPLETENESS and SOURCE QUALITY only.
- It never ranks candidates, judges candidate quality, predicts election
  outcomes, or makes persuasion claims.
- "Readiness" always refers to data readiness, not campaign strength.

Run locally with:
    streamlit run app/streamlit/dashboard.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# app/streamlit/dashboard.py -> repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_GOLD = REPO_ROOT / "data" / "gold"
REPORTS = REPO_ROOT / "reports"

GOLD_DOSSIERS_PATH = DATA_GOLD / "gold_candidate_dossiers.csv"
GOLD_READINESS_PATH = DATA_GOLD / "gold_campaign_readiness.csv"
GOLD_RISK_SIGNALS_PATH = DATA_GOLD / "gold_risk_signals.csv"
TARGET_3_VALIDATION_PATH = REPORTS / "target_3_validation_report.csv"
GOLD_OUTPUTS_VALIDATION_PATH = REPORTS / "gold_outputs_validation_report.csv"

# Columns that must stay text so identifiers like filer IDs keep leading zeros.
STRING_DTYPE_COLUMNS = {"filer_id", "bar_number", "source_id"}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_csv(path: Path) -> pd.DataFrame | None:
    """Load a CSV file into a DataFrame, returning None if it is missing.

    Identifier-like columns (e.g. filer_id) are forced to string dtype so
    that leading zeros are preserved instead of being parsed as integers.
    """
    if not path.exists():
        return None
    dtype_overrides = {col: str for col in STRING_DTYPE_COLUMNS}
    try:
        return pd.read_csv(path, dtype=dtype_overrides)
    except Exception as exc:  # malformed file, permissions, etc.
        st.error(f"Could not read {path.relative_to(REPO_ROOT)}: {exc}")
        return None


def format_currency(value) -> str:
    """Format a numeric value as USD currency, or a placeholder if missing."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Not available"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def format_percentage(value, already_fraction: bool = True) -> str:
    """Format a numeric value as a percentage string.

    Args:
        value: The numeric value to format.
        already_fraction: If True, value is a 0-1 fraction (e.g. 0.055 -> 5.5%).
            If False, value is already on a 0-100 scale.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Not available"
    try:
        pct = float(value) * 100 if already_fraction else float(value)
        return f"{pct:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def safe_get(row: pd.Series, column: str, default: str = "Not available"):
    """Return row[column] if present and non-null, else a default placeholder."""
    if column not in row.index:
        return default
    value = row[column]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    return value


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def inject_custom_css() -> None:
    """Inject the Spartan Judicial brand CSS: civic, restrained, executive."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,500&family=Inter:wght@400;500;600;700&display=swap');

        :root {
            --sj-navy: #1c1f26;
            --sj-navy-light: #2a2e38;
            --sj-maroon: #7a1620;
            --sj-maroon-dark: #5c1018;
            --sj-gold: #b08d57;
            --sj-cream: #f7f4ee;
            --sj-ink: #24262b;
            --sj-muted: #6b6f76;
            --sj-border: #e3ded2;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, sans-serif;
        }

        .stApp {
            background-color: var(--sj-cream);
        }

        /* Hide default Streamlit chrome for a cleaner "product" feel */
        #MainMenu, footer, header[data-testid="stHeader"] {
            visibility: hidden;
            height: 0;
        }

        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 3rem;
            max-width: 1180px;
        }

        h1, h2, h3 {
            font-family: 'Playfair Display', Georgia, serif;
            color: var(--sj-navy);
            letter-spacing: -0.01em;
        }

        /* ---- Hero banner ---- */
        .sj-hero {
            background: linear-gradient(135deg, var(--sj-navy) 0%, var(--sj-navy-light) 100%);
            border-radius: 10px;
            padding: 2.6rem 2.8rem;
            margin-bottom: 1.75rem;
            border: 1px solid #34394480;
            position: relative;
            overflow: hidden;
        }
        .sj-hero::before {
            content: "";
            position: absolute;
            top: 0; left: 0; bottom: 0;
            width: 4px;
            background: var(--sj-maroon);
        }
        .sj-hero-eyebrow {
            color: var(--sj-gold);
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.6rem;
        }
        .sj-hero h1 {
            color: #f5f2ea;
            font-size: 2.15rem;
            margin: 0 0 0.55rem 0;
            font-weight: 700;
        }
        .sj-hero p {
            color: #c7cad2;
            font-size: 1.02rem;
            max-width: 62ch;
            margin: 0;
            line-height: 1.55;
        }

        /* ---- Badge row ---- */
        .sj-badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.6rem;
            margin-top: 1.3rem;
        }
        .sj-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.16);
            color: #e7e4da;
            padding: 0.38rem 0.8rem;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 500;
        }
        .sj-badge .dot {
            width: 7px; height: 7px; border-radius: 50%;
            background: #8fbf8a;
            display: inline-block;
        }

        /* ---- Section headers ---- */
        .sj-section-label {
            color: var(--sj-maroon);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.2rem;
        }
        .sj-section-title {
            font-family: 'Playfair Display', Georgia, serif;
            font-size: 1.55rem;
            color: var(--sj-navy);
            margin: 0 0 0.9rem 0;
        }

        /* ---- Generic card ---- */
        .sj-card {
            background: #ffffff;
            border: 1px solid var(--sj-border);
            border-radius: 8px;
            padding: 1.25rem 1.4rem;
            margin-bottom: 0.9rem;
        }
        .sj-card-accent {
            border-top: 3px solid var(--sj-maroon);
        }

        /* ---- Metric cards ---- */
        .sj-metric-card {
            background: #ffffff;
            border: 1px solid var(--sj-border);
            border-top: 3px solid var(--sj-gold);
            border-radius: 8px;
            padding: 1.1rem 1.3rem;
            height: 100%;
        }
        .sj-metric-label {
            font-size: 0.74rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--sj-muted);
            margin-bottom: 0.35rem;
        }
        .sj-metric-value {
            font-family: 'Playfair Display', Georgia, serif;
            font-size: 2.1rem;
            color: var(--sj-navy);
            line-height: 1.1;
        }

        /* ---- Pipeline ---- */
        .sj-pipeline-wrap {
            display: flex;
            align-items: stretch;
            gap: 0.5rem;
            overflow-x: auto;
            padding-bottom: 0.4rem;
        }
        .sj-pipeline-step {
            flex: 1 1 0;
            min-width: 165px;
            background: #ffffff;
            border: 1px solid var(--sj-border);
            border-radius: 8px;
            padding: 1rem 1.1rem;
        }
        .sj-pipeline-step .step-num {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px; height: 24px;
            border-radius: 50%;
            background: var(--sj-navy);
            color: #f5f2ea;
            font-size: 0.72rem;
            font-weight: 700;
            margin-bottom: 0.55rem;
        }
        .sj-pipeline-step .step-title {
            font-weight: 700;
            color: var(--sj-navy);
            font-size: 0.95rem;
            margin-bottom: 0.3rem;
        }
        .sj-pipeline-step .step-desc {
            color: var(--sj-muted);
            font-size: 0.83rem;
            line-height: 1.4;
        }
        .sj-pipeline-arrow {
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--sj-gold);
            font-size: 1.3rem;
            flex: 0 0 auto;
        }

        /* ---- Profile field grid ---- */
        .sj-field-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.9rem 1.6rem;
        }
        .sj-field {
            border-bottom: 1px solid var(--sj-border);
            padding-bottom: 0.55rem;
        }
        .sj-field-label {
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--sj-muted);
            margin-bottom: 0.25rem;
        }
        .sj-field-value {
            font-size: 1rem;
            color: var(--sj-ink);
            font-weight: 500;
        }

        /* ---- Risk badges ---- */
        .sj-risk-badge {
            display: inline-block;
            padding: 0.18rem 0.65rem;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }
        .sj-risk-high {
            background: #f4dede;
            color: #7a1620;
            border: 1px solid #e3b9bc;
        }
        .sj-risk-medium {
            background: #f8ecd8;
            color: #8a5a1e;
            border: 1px solid #ecd3a6;
        }
        .sj-risk-low {
            background: #e8ede4;
            color: #4a6741;
            border: 1px solid #c9d6bf;
        }

        .sj-risk-card {
            background: #ffffff;
            border: 1px solid var(--sj-border);
            border-left: 4px solid var(--sj-border);
            border-radius: 6px;
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.7rem;
        }
        .sj-risk-card.risk-high { border-left-color: var(--sj-maroon); }
        .sj-risk-card.risk-medium { border-left-color: #c98f3a; }
        .sj-risk-card.risk-low { border-left-color: #6e8f63; }

        .sj-risk-type {
            font-weight: 700;
            color: var(--sj-navy);
            font-size: 0.92rem;
            margin-bottom: 0.3rem;
        }
        .sj-risk-message {
            color: var(--sj-ink);
            font-size: 0.88rem;
            line-height: 1.5;
            margin-bottom: 0.4rem;
        }
        .sj-risk-meta {
            color: var(--sj-muted);
            font-size: 0.78rem;
        }

        /* ---- Caveat panel ---- */
        .sj-caveat-panel {
            background: #fbf7ee;
            border: 1px solid #e6d9b8;
            border-left: 4px solid var(--sj-gold);
            border-radius: 6px;
            padding: 1.1rem 1.4rem;
        }
        .sj-caveat-panel ul {
            margin: 0.3rem 0 0 0;
            padding-left: 1.2rem;
        }
        .sj-caveat-panel li {
            color: var(--sj-ink);
            font-size: 0.9rem;
            line-height: 1.65;
            margin-bottom: 0.35rem;
        }

        /* ---- Divider ---- */
        .sj-divider {
            border: none;
            border-top: 1px solid var(--sj-border);
            margin: 2.2rem 0 1.6rem 0;
        }

        .sj-note {
            font-size: 0.85rem;
            color: var(--sj-muted);
            font-style: italic;
            margin-top: 0.5rem;
        }

        .sj-explainer {
            color: var(--sj-ink);
            font-size: 0.95rem;
            line-height: 1.6;
            background: #ffffff;
            border: 1px solid var(--sj-border);
            border-radius: 8px;
            padding: 1rem 1.3rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def render_section_header(label: str, title: str) -> None:
    """Render a consistent section eyebrow label + title."""
    st.markdown(
        f"""
        <div class="sj-section-label">{label}</div>
        <div class="sj-section-title">{title}</div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str) -> None:
    """Render a single branded metric card. Call inside a st.columns() cell."""
    st.markdown(
        f"""
        <div class="sj-metric-card">
            <div class="sj-metric-label">{label}</div>
            <div class="sj-metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pipeline_overview() -> None:
    """Render the bronze -> silver -> validation -> gold -> dashboard pipeline."""
    render_section_header("How this works", "Pipeline Overview")

    steps = [
        ("1", "Bronze", "Preserves original source files exactly as collected."),
        ("2", "Silver", "Standardizes messy fields into consistent formats."),
        ("3", "Validation", "Checks that data matches the expected schema and types."),
        ("4", "Gold", "Produces campaign-ready data outputs for the dashboard."),
        ("5", "Dashboard", "Lets the team inspect profiles, readiness, and risks."),
    ]

    step_html = ""
    for i, (num, title, desc) in enumerate(steps):
        step_html += f"""
        <div class="sj-pipeline-step">
            <div class="step-num">{num}</div>
            <div class="step-title">{title}</div>
            <div class="step-desc">{desc}</div>
        </div>
        """
        if i < len(steps) - 1:
            step_html += '<div class="sj-pipeline-arrow">&rarr;</div>'

    st.markdown(f'<div class="sj-pipeline-wrap">{step_html}</div>', unsafe_allow_html=True)


def render_candidate_profile(row: pd.Series) -> None:
    """Render the full candidate profile card for a single dossier row."""
    render_section_header("Candidate Profile", str(safe_get(row, "candidate_name")))

    fields = [
        ("Candidate Name", safe_get(row, "candidate_name")),
        ("Party", safe_get(row, "party")),
        ("Court Name", safe_get(row, "court_name")),
        ("Court Type", safe_get(row, "court_type")),
        ("Incumbent Status", safe_get(row, "incumbent_status")),
        ("Bar Status", safe_get(row, "bar_status")),
        ("Licensed Since", safe_get(row, "licensed_since")),
        ("Public Discipline Flag", safe_get(row, "public_discipline_flag")),
        ("TEC Filer ID", safe_get(row, "filer_id")),
        ("Total Contributions", format_currency(row.get("total_contributions"))),
        ("Total Expenditures", format_currency(row.get("total_expenditures"))),
        ("OCA Case Category", safe_get(row, "oca_case_category")),
        ("Active Pending Total", safe_get(row, "active_pending_total")),
        ("Long Pending Count", safe_get(row, "long_pending_count")),
        ("Long Pending Threshold", safe_get(row, "long_pending_threshold")),
        ("Long Pending %", format_percentage(row.get("long_pending_pct"))),
        ("SCJC Result", safe_get(row, "scjc_result")),
    ]

    field_html = ""
    for label, value in fields:
        field_html += f"""
        <div class="sj-field">
            <div class="sj-field-label">{label}</div>
            <div class="sj-field-value">{value}</div>
        </div>
        """

    st.markdown(
        f'<div class="sj-card"><div class="sj-field-grid">{field_html}</div></div>',
        unsafe_allow_html=True,
    )


def render_readiness_section(row: pd.Series | None) -> None:
    """Render the data-readiness metrics for the selected candidate.

    Deliberately labeled "Data Readiness" rather than "Campaign Strength" —
    this measures field completeness of the prototype dossier, not candidate
    quality or electoral competitiveness.
    """
    render_section_header("Prototype Data Completeness", "Data Readiness")

    if row is None:
        st.info("No readiness record found for this candidate.")
        return

    score = row.get("readiness_score")
    label = safe_get(row, "readiness_label")
    fields_complete = safe_get(row, "fields_complete")
    fields_possible = safe_get(row, "fields_possible")
    missing = safe_get(row, "missing_or_review_fields", default="None")

    col1, col2 = st.columns([2, 1])
    with col1:
        try:
            score_val = float(score)
            st.progress(min(max(score_val, 0.0), 1.0))
            st.markdown(f"**Readiness score:** {score_val * 100:.0f}% &nbsp;·&nbsp; **Label:** {label}")
        except (TypeError, ValueError):
            st.markdown(f"**Readiness score:** Not available &nbsp;·&nbsp; **Label:** {label}")
        st.markdown(
            f"**Fields complete:** {fields_complete} of {fields_possible} &nbsp;·&nbsp; "
            f"**Missing / needs review:** {missing}"
        )
    with col2:
        render_metric_card("Fields Complete", f"{fields_complete}/{fields_possible}")

    st.markdown(
        """
        <p class="sj-note">
        This score measures completeness of the current prototype fields.
        It does not evaluate candidate quality, election competitiveness, or voter support.
        </p>
        """,
        unsafe_allow_html=True,
    )


def render_risk_signals(candidate_risks: pd.DataFrame) -> None:
    """Render risk-signal cards for the selected candidate's risk rows."""
    render_section_header("Interpretation Risk", "Risk Signals")

    if candidate_risks.empty:
        st.info("No risk signals recorded for this candidate.")
        return

    level_class_map = {"high": "risk-high", "medium": "risk-medium", "low": "risk-low"}
    badge_class_map = {"high": "sj-risk-high", "medium": "sj-risk-medium", "low": "sj-risk-low"}

    for _, risk in candidate_risks.iterrows():
        level_raw = str(safe_get(risk, "risk_level", default="")).strip().lower()
        card_class = level_class_map.get(level_raw, "")
        badge_class = badge_class_map.get(level_raw, "sj-risk-medium")
        risk_type = safe_get(risk, "risk_type")
        risk_level_display = safe_get(risk, "risk_level")
        risk_message = safe_get(risk, "risk_message")
        source_id = safe_get(risk, "source_id")
        action = safe_get(risk, "recommended_action")

        st.markdown(
            f"""
            <div class="sj-risk-card {card_class}">
                <div class="sj-risk-type">
                    {risk_type}
                    <span class="sj-risk-badge {badge_class}">{risk_level_display}</span>
                </div>
                <div class="sj-risk-message">{risk_message}</div>
                <div class="sj-risk-meta">Source: {source_id} &nbsp;·&nbsp; Recommended action: {action}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Spartan Judicial Campaign Data Platform",
        page_icon="⚖️",
        layout="wide",
    )
    inject_custom_css()

    # ---- Load data ----
    dossiers_df = load_csv(GOLD_DOSSIERS_PATH)
    readiness_df = load_csv(GOLD_READINESS_PATH)
    risk_df = load_csv(GOLD_RISK_SIGNALS_PATH)
    target_3_validation_df = load_csv(TARGET_3_VALIDATION_PATH)
    gold_validation_df = load_csv(GOLD_OUTPUTS_VALIDATION_PATH)

    # ---- 1. Hero header ----
    validation_passed = (
        target_3_validation_df is not None
        and not target_3_validation_df.empty
        and (target_3_validation_df["validation_status"] == "passed").all()
    )
    st.markdown(
        f"""
        <div class="sj-hero">
            <div class="sj-hero-eyebrow">Internal Prototype &middot; Data Platform</div>
            <h1>Spartan Judicial Campaign Data Platform</h1>
            <p>Prototype dashboard for candidate dossiers, data readiness, source quality,
            and interpretation-risk tracking.</p>
            <div class="sj-badge-row">
                <span class="sj-badge"><span class="dot"></span>Target campaigns: 3</span>
                <span class="sj-badge"><span class="dot"></span>Validation: {"Passed" if validation_passed else "Review needed"}</span>
                <span class="sj-badge"><span class="dot"></span>Gold outputs: Generated</span>
                <span class="sj-badge"><span class="dot"></span>Risk signals: Generated</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- 2. Executive summary ----
    render_section_header("At a Glance", "Executive Summary")

    candidates_processed = len(dossiers_df) if dossiers_df is not None else 0
    gold_dossier_rows = len(dossiers_df) if dossiers_df is not None else 0
    validation_pass_count = (
        int((target_3_validation_df["validation_status"] == "passed").sum())
        if target_3_validation_df is not None
        else 0
    )
    total_risk_signals = len(risk_df) if risk_df is not None else 0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_metric_card("Candidates Processed", str(candidates_processed))
    with m2:
        render_metric_card("Gold Dossier Rows", str(gold_dossier_rows))
    with m3:
        render_metric_card("Validation Pass Count", str(validation_pass_count))
    with m4:
        render_metric_card("Total Risk Signals", str(total_risk_signals))

    st.markdown(
        """
        <div class="sj-explainer" style="margin-top: 0.9rem;">
        This dashboard sits on top of a bronze &rarr; silver &rarr; gold data pipeline.
        Raw public-source data is preserved, cleaned, validated, and converted into
        dashboard-ready outputs.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    # ---- 3. Pipeline overview ----
    render_pipeline_overview()

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    # ---- 4. Candidate selector ----
    render_section_header("Select a Race", "Candidate Selector")

    candidate_options = ["Joe Radler", "Paul Sullivan", "Tami Pierce"]
    selected_candidate = st.selectbox("Choose a candidate", candidate_options, label_visibility="collapsed")

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    # ---- 5. Candidate profile / 6. Readiness / 7. Risk signals ----
    if dossiers_df is not None and "candidate_name" in dossiers_df.columns:
        candidate_row_matches = dossiers_df[dossiers_df["candidate_name"] == selected_candidate]
        if not candidate_row_matches.empty:
            render_candidate_profile(candidate_row_matches.iloc[0])
        else:
            st.warning(f"No dossier record found for {selected_candidate}.")
    else:
        st.error(f"Candidate dossier file not found or unreadable: {GOLD_DOSSIERS_PATH.relative_to(REPO_ROOT)}")

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    if readiness_df is not None and "candidate_name" in readiness_df.columns:
        readiness_matches = readiness_df[readiness_df["candidate_name"] == selected_candidate]
        render_readiness_section(readiness_matches.iloc[0] if not readiness_matches.empty else None)
    else:
        render_section_header("Prototype Data Completeness", "Data Readiness")
        st.error(f"Readiness file not found or unreadable: {GOLD_READINESS_PATH.relative_to(REPO_ROOT)}")

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    if risk_df is not None and "candidate_name" in risk_df.columns:
        candidate_risks = risk_df[risk_df["candidate_name"] == selected_candidate]
        render_risk_signals(candidate_risks)
    else:
        render_section_header("Interpretation Risk", "Risk Signals")
        st.error(f"Risk signals file not found or unreadable: {GOLD_RISK_SIGNALS_PATH.relative_to(REPO_ROOT)}")

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    # ---- 8. Source caveats ----
    render_section_header("Read Before Interpreting", "Source Caveats")
    st.markdown(
        """
        <div class="sj-caveat-panel">
        <ul>
            <li>OCA metrics are court-level context for the seat, not individual candidate performance.</li>
            <li>For challengers, current court metrics should not be framed as the challenger's personal record.</li>
            <li>For incumbents, court-level metrics may still reflect staffing, case volume, case type, and broader system conditions.</li>
            <li>TEC values are latest report-period totals, not lifetime or full-cycle totals unless all reports are reconciled.</li>
            <li>SCJC results are source-scoped. &ldquo;No matching public sanction found in checked pages&rdquo; should not be shortened to &ldquo;no sanctions.&rdquo;</li>
            <li>State Bar public disciplinary information is not a full background check.</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    # ---- 9. All-candidates overview ----
    render_section_header("Cross-Candidate View", "All Candidates Overview")

    if dossiers_df is not None and readiness_df is not None:
        overview_df = dossiers_df[["candidate_name", "court_name", "incumbent_status", "overall_confidence"]].merge(
            readiness_df[["candidate_name", "readiness_score", "readiness_label"]],
            on="candidate_name",
            how="left",
        )
        overview_df = overview_df[
            ["candidate_name", "court_name", "incumbent_status", "readiness_score", "readiness_label", "overall_confidence"]
        ]
        overview_df = overview_df.rename(
            columns={
                "candidate_name": "Candidate",
                "court_name": "Court",
                "incumbent_status": "Incumbent Status",
                "readiness_score": "Readiness Score",
                "readiness_label": "Readiness Label",
                "overall_confidence": "Overall Confidence",
            }
        )
        st.dataframe(overview_df, hide_index=True, use_container_width=True)
    else:
        st.error("Could not build the all-candidates overview because a required gold file is missing.")

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    # ---- 10. Data quality / validation ----
    render_section_header("Pipeline Integrity", "Data Quality & Validation")
    st.markdown(
        """
        <div class="sj-explainer">
        The validation reports confirm that the cleaned target dossier and generated gold
        outputs match expected schema/column requirements.
        </div>
        """,
        unsafe_allow_html=True,
    )

    vcol1, vcol2 = st.columns(2)
    with vcol1:
        st.markdown("**Target-3 Dossier Validation**")
        if target_3_validation_df is not None:
            st.dataframe(target_3_validation_df, hide_index=True, use_container_width=True)
        else:
            st.error(f"File not found: {TARGET_3_VALIDATION_PATH.relative_to(REPO_ROOT)}")
    with vcol2:
        st.markdown("**Gold Outputs Validation**")
        if gold_validation_df is not None:
            st.dataframe(gold_validation_df, hide_index=True, use_container_width=True)
        else:
            st.error(f"File not found: {GOLD_OUTPUTS_VALIDATION_PATH.relative_to(REPO_ROOT)}")

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)

    # ---- 11. Source lineage / next-review ----
    render_section_header("Open Items", "Source Lineage & Next Review")
    st.markdown(
        """
        <div class="sj-card sj-card-accent">
        <p style="color: var(--sj-ink); font-size: 0.92rem; line-height: 1.7; margin: 0;">
        The following items still need direct source verification before this prototype
        could be treated as production-ready:
        </p>
        <ul style="color: var(--sj-ink); font-size: 0.9rem; line-height: 1.7; margin: 0.6rem 0 0 0;">
            <li>Direct TEC report URLs (current campaign-finance links are source/search pages, not direct filer reports).</li>
            <li>Direct OCA source URL for the court-level activity metrics cited in each dossier.</li>
            <li>Direct SCJC archive/source URL for the sanctions pages checked.</li>
            <li>Confirmation of which fiscal years were checked for the SCJC review.</li>
            <li>Manual identity verification where a candidate name match required judgment.</li>
            <li>Official election/county source verification for the candidate roster itself.</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
