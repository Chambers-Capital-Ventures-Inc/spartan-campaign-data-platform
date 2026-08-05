"""
Spartan Judicial Candidate Lookup — Streamlit app.

An early customer-facing civic information lookup prototype. A voter,
campaign stakeholder, or other non-technical user can search for or browse
one of three target Harris County judicial candidates and read a readable,
plain-English public-record profile in one place.

Data comes from a bronze -> silver -> validation -> gold pipeline, but that
backend vocabulary is intentionally kept out of the main user journey. It
only appears inside the "About the data pipeline" expander near the bottom,
for technical reviewers.

Neutrality rules (do not violate when editing):
- Never rank or compare candidates as better/worse.
- Never tell a user who to vote for, and never predict an election outcome.
- Never call anything corruption, misconduct, good, bad, strong, or weak.
- "Profile completeness" describes prototype DATA COMPLETENESS only — never
  candidate quality, judicial performance, or electability.
- All narrative copy is generated from loaded CSV fields via deterministic
  template functions, not hardcoded per-candidate text and not an LLM.

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

DOSSIERS_PATH = DATA_GOLD / "gold_candidate_dossiers.csv"
READINESS_PATH = DATA_GOLD / "gold_campaign_readiness.csv"
RISK_SIGNALS_PATH = DATA_GOLD / "gold_risk_signals.csv"
TARGET_3_VALIDATION_PATH = REPORTS / "target_3_validation_report.csv"
GOLD_OUTPUTS_VALIDATION_PATH = REPORTS / "gold_outputs_validation_report.csv"

# Identifier-like columns that must stay text so leading zeros survive.
STRING_DTYPE_COLUMNS = {"filer_id", "bar_number", "source_id"}

PARTY_LABELS = {"R": "Republican", "D": "Democratic", "I": "Independent"}

# Friendlier labels for risk_type values, shown as "context" cards rather
# than raw internal risk-signal terminology.
CONTEXT_LABELS = {
    "court_metric_interpretation": "Court metric context",
    "challenger_interpretation": "Challenger context",
    "incumbent_interpretation": "Incumbent context",
    "campaign_finance_scope": "Campaign finance scope",
    "scjc_scope": "Public sanctions archive scope",
    "source_link_specificity": "Source link review",
    "high_long_pending_context": "Long-pending case context",
}


# ---------------------------------------------------------------------------
# Data loading + formatting helpers
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


def get_initials(name: str) -> str:
    """Derive a two-letter initials string from a candidate's full name."""
    if not name or not isinstance(name, str):
        return "?"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _safe_get(row: pd.Series, column: str, default: str = "Not available"):
    """Return row[column] if present and non-null, else a default placeholder."""
    if row is None or column not in row.index:
        return default
    value = row[column]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    return value


def get_candidate_matches(df: pd.DataFrame | None, query: str) -> pd.DataFrame:
    """Return rows whose candidate_name contains query (case-insensitive)."""
    if df is None or df.empty or not query:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    mask = df["candidate_name"].str.contains(query, case=False, na=False)
    return df[mask]


def get_candidate_row(df: pd.DataFrame | None, candidate_name: str) -> pd.Series | None:
    """Return the dossier row for candidate_name, or None if not found."""
    if df is None or "candidate_name" not in df.columns:
        return None
    matches = df[df["candidate_name"] == candidate_name]
    if matches.empty:
        return None
    return matches.iloc[0]


def get_readiness_row(df: pd.DataFrame | None, candidate_name: str) -> pd.Series | None:
    """Return the profile-completeness row for candidate_name, or None if not found."""
    if df is None or "candidate_name" not in df.columns:
        return None
    matches = df[df["candidate_name"] == candidate_name]
    if matches.empty:
        return None
    return matches.iloc[0]


def get_candidate_context_rows(df: pd.DataFrame | None, candidate_name: str) -> pd.DataFrame:
    """Return all public-record context (risk signal) rows for a candidate."""
    if df is None or "candidate_name" not in df.columns:
        return pd.DataFrame()
    return df[df["candidate_name"] == candidate_name]


# ---------------------------------------------------------------------------
# Narrative generation helpers (rule-based templates, no LLM, no hardcoding)
# ---------------------------------------------------------------------------

def explain_candidate_summary(row: pd.Series) -> str:
    """Build a short, neutral plain-English summary paragraph for a candidate."""
    name = _safe_get(row, "candidate_name", "This candidate")
    party_code = str(_safe_get(row, "party", "")).strip()
    party = PARTY_LABELS.get(party_code, party_code or "an unspecified-party")
    court_name = _safe_get(row, "court_name", "an unspecified court")

    return (
        f"{name} is listed in this prototype as a {party} candidate for the "
        f"{court_name}. This profile brings together public professional "
        f"information, a campaign finance snapshot, court-level context for the "
        f"seat, and a public sanctions archive check."
    )


def explain_finance_snapshot(row: pd.Series) -> str:
    """Build a plain-English explanation of the campaign finance snapshot."""
    return (
        "This prototype captured a campaign finance snapshot from the Texas "
        "Ethics Commission records. The contribution and expenditure values "
        "shown here reflect the selected/latest report-period totals captured "
        "in the prototype, not lifetime or full-cycle totals."
    )


def explain_court_context(row: pd.Series) -> str:
    """Build a plain-English, number-grounded explanation of court-level context."""
    case_category = str(_safe_get(row, "oca_case_category", "court")).strip()
    active_total = row.get("active_pending_total")
    long_count = row.get("long_pending_count")
    long_pct = row.get("long_pending_pct")

    sentence = (
        "This court-level context describes the court seat associated with the "
        "race. It should not be read as individual candidate performance."
    )

    if pd.notna(active_total) and pd.notna(long_count) and pd.notna(long_pct):
        try:
            active_total_int = int(float(active_total))
            long_count_int = int(float(long_count))
            pct_str = format_percentage(long_pct)
            sentence = (
                f"According to the court-level dataset used in this prototype, "
                f"{long_count_int:,} of {active_total_int:,} active pending "
                f"{case_category} cases were classified as long-pending, or "
                f"about {pct_str}. " + sentence
            )
        except (TypeError, ValueError):
            pass

    incumbent_status = str(_safe_get(row, "incumbent_status", "")).strip().lower()
    if incumbent_status == "challenger":
        sentence += (
            " Because this candidate is a challenger, current court metrics "
            "describe the seat they are running for, not their personal "
            "judicial record."
        )
    elif incumbent_status == "incumbent":
        sentence += (
            " Because this candidate is an incumbent, the court-level data may "
            "be more directly relevant to the seat they hold, but it still may "
            "reflect staffing, filings, case mix, and broader court-system "
            "conditions."
        )

    return sentence


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def inject_custom_css() -> None:
    """Inject the Spartan Judicial brand CSS: civic, restrained, welcoming."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,600;0,700;1,500&family=Inter:wght@400;500;600;700&display=swap');

        :root {
            --sj-navy: #1c1f26;
            --sj-navy-light: #2a2e38;
            --sj-maroon: #7a1620;
            --sj-gold: #b08d57;
            --sj-cream: #f7f4ee;
            --sj-ink: #24262b;
            --sj-muted: #6b6f76;
            --sj-border: #e3ded2;
        }

        html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
        .stApp { background-color: var(--sj-cream); }
        #MainMenu, footer { visibility: hidden; height: 0; }
        .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 980px; }
        h1, h2, h3, h4 { font-family: 'Playfair Display', Georgia, serif; color: var(--sj-navy); letter-spacing: -0.01em; }

        /* ---- Landing hero ---- */
        .sj-hero {
            text-align: center;
            padding: 3rem 1rem 1.5rem 1rem;
        }
        .sj-hero-eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: #a4703c;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            margin-bottom: 1rem;
        }
        .sj-hero h1 {
            font-size: 2.5rem;
            margin: 0 0 0.9rem 0;
            line-height: 1.2;
        }
        .sj-hero p.sj-subtitle {
            font-size: 1.15rem;
            color: #3d4148;
            max-width: 640px;
            margin: 0 auto 1.1rem auto;
        }
        .sj-hero p.sj-desc {
            font-size: 0.98rem;
            color: #5b5f66;
            max-width: 600px;
            margin: 0 auto 0.5rem auto;
            line-height: 1.65;
        }
        .sj-hero-footnote {
            font-size: 0.85rem;
            color: #8a8d92;
            margin-top: 1.4rem;
        }

        /* ---- Section headers ---- */
        .sj-section-label {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            color: var(--sj-gold);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 0.3rem;
        }
        .sj-section-label::before { content: ""; display: inline-block; width: 20px; height: 2px; background: var(--sj-maroon); }
        .sj-section-title { font-family: 'Playfair Display', Georgia, serif; font-size: 1.5rem; color: var(--sj-navy); margin: 0 0 0.35rem 0; }
        .sj-section-sub { color: var(--sj-muted); font-size: 0.92rem; margin: 0 0 1rem 0; }

        /* ---- Candidate browse / search-result cards ---- */
        .sj-candidate-card {
            background: #ffffff;
            border: 1px solid var(--sj-border);
            border-top: 3px solid var(--sj-gold);
            border-radius: 8px;
            padding: 1.2rem 1.3rem;
            margin-bottom: 0.9rem;
        }
        .sj-initials-circle {
            width: 48px; height: 48px; border-radius: 50%;
            background: var(--sj-navy); color: #f5f2ea;
            font-family: 'Playfair Display', Georgia, serif;
            font-size: 1.05rem; font-weight: 700;
            display: flex; align-items: center; justify-content: center;
        }
        .sj-candidate-card .cand-name { font-family: 'Playfair Display', Georgia, serif; font-size: 1.12rem; color: var(--sj-navy); font-weight: 700; margin-bottom: 0.15rem; }
        .sj-candidate-card .cand-court { color: var(--sj-ink); font-size: 0.87rem; margin-bottom: 0.4rem; }

        .sj-badge {
            display: inline-block; padding: 0.18rem 0.65rem; border-radius: 999px;
            font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em; margin-right: 0.35rem;
        }
        .sj-badge-incumbent { background: #eef3ee; color: #2f5d38; }
        .sj-badge-challenger { background: #f2ece0; color: #8a5a20; }
        .sj-badge-party-r { background: #fbeaea; color: #7a1220; }
        .sj-badge-party-d { background: #e8eef7; color: #1e4e8c; }

        /* ---- Profile header ---- */
        .sj-profile-header {
            background: linear-gradient(135deg, var(--sj-navy) 0%, var(--sj-navy-light) 100%);
            border-radius: 10px;
            padding: 1.7rem 1.9rem;
            margin-bottom: 1.3rem;
        }
        .sj-profile-header h2 { color: #f5f2ea; margin: 0 0 0.35rem 0; }
        .sj-profile-header .sj-profile-sub { color: #c7cad2; font-size: 0.95rem; }

        /* ---- Field grid ---- */
        .sj-card { background: #ffffff; border: 1px solid var(--sj-border); border-radius: 8px; padding: 1.2rem 1.35rem; }
        .sj-field-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 0.9rem 1.5rem; }
        .sj-field { border-bottom: 1px solid var(--sj-border); padding-bottom: 0.5rem; }
        .sj-field-label { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--sj-muted); margin-bottom: 0.2rem; }
        .sj-field-value { font-size: 0.98rem; color: var(--sj-ink); font-weight: 500; }

        /* ---- Narrative / explainer text ---- */
        .sj-narrative {
            color: var(--sj-ink); font-size: 0.97rem; line-height: 1.7;
            background: #ffffff; border: 1px solid var(--sj-border);
            border-left: 4px solid var(--sj-gold); border-radius: 6px;
            padding: 1.1rem 1.35rem; margin-top: 0.8rem;
        }

        /* ---- Context cards (Public Record Notes tab) ---- */
        .sj-context-card {
            background: #ffffff; border: 1px solid var(--sj-border);
            border-left: 4px solid var(--sj-navy); border-radius: 6px;
            padding: 0.95rem 1.15rem; margin-bottom: 0.7rem;
        }
        .sj-context-title { font-weight: 700; color: var(--sj-navy); font-size: 0.9rem; margin-bottom: 0.3rem; }
        .sj-context-message { color: var(--sj-ink); font-size: 0.88rem; line-height: 1.55; margin-bottom: 0.35rem; }
        .sj-context-action { color: var(--sj-muted); font-size: 0.8rem; }

        .sj-divider { border: none; border-top: 1px solid var(--sj-border); margin: 1.9rem 0 1.5rem 0; }

        .sj-caveat-list li { margin-bottom: 0.55rem; color: #3d4148; line-height: 1.55; font-size: 0.94rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _field_grid_html(fields: list[tuple[str, str]]) -> str:
    """Build the inner HTML for a labeled field grid card."""
    items = "".join(
        f'<div class="sj-field"><div class="sj-field-label">{label}</div>'
        f'<div class="sj-field-value">{value}</div></div>'
        for label, value in fields
    )
    return f'<div class="sj-card"><div class="sj-field-grid">{items}</div></div>'


def _status_badge_html(incumbent_status) -> str:
    css_class = "sj-badge-incumbent" if str(incumbent_status).strip().lower() == "incumbent" else "sj-badge-challenger"
    return f'<span class="sj-badge {css_class}">{incumbent_status}</span>'


def _party_badge_html(party) -> str:
    code = str(party).strip().upper()
    css_class = "sj-badge-party-r" if code == "R" else "sj-badge-party-d"
    label = PARTY_LABELS.get(code, code or "Unknown")
    return f'<span class="sj-badge {css_class}">{label}</span>'


# ---------------------------------------------------------------------------
# Render: landing hero
# ---------------------------------------------------------------------------

def render_hero() -> None:
    """Render the minimalist landing page with a Get Started call to action.

    Deliberately excludes any backend/pipeline vocabulary or metrics — this
    is meant to feel like a public product front door, not an ops dashboard.
    """
    st.markdown(
        """
        <div class="sj-hero">
            <div class="sj-hero-eyebrow">Harris County &middot; Texas</div>
            <h1>Spartan Judicial Candidate Lookup</h1>
            <p class="sj-subtitle">
                Public records, court context, and campaign finance information in
                one readable profile.
            </p>
            <p class="sj-desc">
                Judicial races can be hard to research because information is
                scattered across election pages, attorney profiles, campaign
                finance records, court datasets, and public archives. This
                prototype brings those records into one easier-to-read candidate
                profile.
            </p>
        </div>

        """,
        unsafe_allow_html=True,
    )

    _, center, _ = st.columns([1, 1, 1])
    with center:
        if st.button("Get Started", type="primary", width="stretch"):
            st.session_state.app_started = True
            st.rerun()

    st.markdown(
        '<div class="sj-hero-footnote" style="text-align:center;">'
        "Prototype currently includes three Harris County judicial candidates."
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Render: search + browse
# ---------------------------------------------------------------------------
def make_widget_key(prefix: str, name: str, index: int) -> str:
    """Create a stable unique Streamlit widget key.

    Streamlit requires every widget key to be unique across the whole rendered
    page. Candidate names alone are not safe because the same candidate can
    appear in search results and browse cards at the same time.
    """
    safe_name = (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace(".", "")
        .replace("'", "")
        .replace('"', "")
    )
    return f"{prefix}_{index}_{safe_name}"


def _render_candidate_result_card(
    row: pd.Series,
    index: int,
    key_prefix: str,
) -> None:
    """Render one candidate result/browse card with a unique profile button key."""
    name = _safe_get(row, "candidate_name", "Unknown candidate")
    court_name = _safe_get(row, "court_name")
    incumbent_status = _safe_get(row, "incumbent_status")
    party = row.get("party", "")

    st.markdown('<div class="sj-candidate-card">', unsafe_allow_html=True)

    bubble_col, info_col, button_col = st.columns([1, 5, 2])

    with bubble_col:
        st.markdown(
            f'<div class="sj-initials-circle">{get_initials(str(name))}</div>',
            unsafe_allow_html=True,
        )

    with info_col:
        st.markdown(
            f"""
            <div class="cand-name">{name}</div>
            <div class="cand-court">{court_name}</div>
            {_status_badge_html(incumbent_status)}
            {_party_badge_html(party)}
            """,
            unsafe_allow_html=True,
        )

    with button_col:
        if st.button(
            "View profile",
            key=make_widget_key(key_prefix, str(name), index),
            width="stretch",
        ):
            st.session_state.selected_candidate = name
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

def render_search_interface(dossiers_df: pd.DataFrame | None) -> None:
    """Render the free-text candidate name search box with live-filtered result cards."""
    query = st.text_input(
        "Search by candidate name",
        placeholder="Start typing a name, e.g. ‘Rad’",
        label_visibility="collapsed",
    )
    if not query:
        st.caption("Start typing to see matching candidates.")
        return

    matches = get_candidate_matches(dossiers_df, query)
    if matches.empty:
        st.info("No candidates in this prototype match that search.")
        return

    for index, (_, row) in enumerate(matches.iterrows()):
        _render_candidate_result_card(
            row=row,
            index=index,
            key_prefix="search_result",
    )


def render_client_cards(dossiers_df: pd.DataFrame | None) -> None:
    """Render candidate cards for every candidate currently covered by the prototype."""
    if dossiers_df is None or dossiers_df.empty:
        st.info("No candidate records are currently available.")
        return
    for index, (_, row) in enumerate(dossiers_df.iterrows()):
        _render_candidate_result_card(
            row=row,
            index=index,
            key_prefix="browse_client",
        )


# ---------------------------------------------------------------------------
# Render: candidate profile tabs
# ---------------------------------------------------------------------------

def render_overview_tab(dossier_row: pd.Series, readiness_row: pd.Series | None) -> None:
    """Render the Overview tab: race, status, profile completeness, sanctions check."""
    st.markdown(f'<div class="sj-narrative">{explain_candidate_summary(dossier_row)}</div>', unsafe_allow_html=True)
    st.write("")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Race", _safe_get(dossier_row, "court_name"))
        st.caption(_safe_get(dossier_row, "court_type", ""))
    with col2:
        st.metric("Candidate status", _safe_get(dossier_row, "incumbent_status"))
    with col3:
        if readiness_row is not None:
            score = readiness_row.get("readiness_score")
            st.metric("Profile completeness", format_percentage(score) if pd.notna(score) else "Not available")
            fields_complete = readiness_row.get("fields_complete")
            fields_possible = readiness_row.get("fields_possible")
            if pd.notna(fields_complete) and pd.notna(fields_possible):
                st.caption(f"{int(fields_complete)} of {int(fields_possible)} tracked fields filled")
        else:
            st.metric("Profile completeness", "Not available")
    with col4:
        scjc_result = str(_safe_get(dossier_row, "scjc_result", ""))
        short_status = "No match found in checked pages" if "no matching" in scjc_result.lower() else "See Public Record Notes"
        st.metric("Public sanctions check", short_status)

    st.markdown(
        """
        <div class="sj-narrative">
        Profile completeness measures whether the currently tracked prototype
        fields are filled. It does not evaluate candidate quality, election
        competitiveness, or voter support.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_professional_background_tab(dossier_row: pd.Series) -> None:
    """Render the Professional Background tab: bar status, licensure, discipline flag."""
    fields = [
        ("Bar Status", _safe_get(dossier_row, "bar_status")),
        ("Licensed Since", _safe_get(dossier_row, "licensed_since")),
        ("Public Discipline Flag", _safe_get(dossier_row, "public_discipline_flag")),
    ]
    st.markdown(_field_grid_html(fields), unsafe_allow_html=True)
    st.markdown(
        """
        <div class="sj-narrative">
        The State Bar fields summarize public attorney profile information
        captured for the prototype. This is not a full background check.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_campaign_finance_tab(dossier_row: pd.Series) -> None:
    """Render the Campaign Finance tab: filer ID, contributions, expenditures."""
    fields = [
        ("TEC Filer ID", _safe_get(dossier_row, "filer_id")),
        ("Total Contributions", format_currency(dossier_row.get("total_contributions"))),
        ("Total Expenditures", format_currency(dossier_row.get("total_expenditures"))),
    ]
    st.markdown(_field_grid_html(fields), unsafe_allow_html=True)
    st.markdown(f'<div class="sj-narrative">{explain_finance_snapshot(dossier_row)}</div>', unsafe_allow_html=True)


def render_court_context_tab(dossier_row: pd.Series) -> None:
    """Render the Court Context tab: OCA case category and pending-case metrics."""
    fields = [
        ("OCA Case Category", str(_safe_get(dossier_row, "oca_case_category")).title()),
        ("Active Pending Total", _safe_get(dossier_row, "active_pending_total")),
        ("Long Pending Count", _safe_get(dossier_row, "long_pending_count")),
        ("Long Pending Threshold", _safe_get(dossier_row, "long_pending_threshold")),
        ("Long Pending %", format_percentage(dossier_row.get("long_pending_pct"))),
    ]
    st.markdown(_field_grid_html(fields), unsafe_allow_html=True)
    st.markdown(f'<div class="sj-narrative">{explain_court_context(dossier_row)}</div>', unsafe_allow_html=True)


def render_public_record_notes_tab(context_rows: pd.DataFrame) -> None:
    """Render 'Important context before interpreting this profile' using public-record notes."""
    st.markdown("#### Important context before interpreting this profile")

    if context_rows.empty:
        st.info("No additional context notes are available for this candidate.")
        return

    for _, row in context_rows.iterrows():
        risk_type = str(_safe_get(row, "risk_type", "")).strip()
        title = CONTEXT_LABELS.get(risk_type, risk_type.replace("_", " ").capitalize())
        st.markdown(
            f"""
            <div class="sj-context-card">
                <div class="sj-context-title">{title}</div>
                <div class="sj-context-message">{_safe_get(row, 'risk_message')}</div>
                <div class="sj-context-action">Recommended next step: {_safe_get(row, 'recommended_action')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("Technical / source details"):
        st.dataframe(
            context_rows[["risk_type", "source_id"]].rename(
                columns={"risk_type": "Context type", "source_id": "Source reference"}
            ),
            hide_index=True,
            width="stretch",
        )


def render_sources_caveats_tab() -> None:
    """Render the Sources & Caveats tab with fixed, source-scoped caveat language."""
    st.markdown("#### How to read this profile")
    st.markdown(
        """
        <ul class="sj-caveat-list">
            <li>OCA metrics are court-level context for the seat, not individual candidate performance.</li>
            <li>For challengers, current court metrics should not be framed as the challenger's personal record.</li>
            <li>For incumbents, court-level metrics may still reflect staffing, case volume, case type, and broader system conditions.</li>
            <li>TEC values are report-period totals, not lifetime or full-cycle totals unless all reports are reconciled.</li>
            <li>SCJC results are source-scoped. "No matching public sanction found in checked pages" should not be shortened to "no sanctions."</li>
            <li>State Bar public disciplinary information is not a full background check.</li>
        </ul>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Items still needing review")
    st.markdown(
        """
        <ul class="sj-caveat-list">
            <li>Direct TEC report URLs</li>
            <li>Direct OCA source URL</li>
            <li>Direct SCJC archive/source URL</li>
            <li>Fiscal years checked for SCJC</li>
            <li>Official election/county source verification for candidate roster</li>
            <li>Manual identity verification where needed</li>
        </ul>
        """,
        unsafe_allow_html=True,
    )


def render_candidate_profile(
    candidate_name: str,
    dossiers_df: pd.DataFrame | None,
    readiness_df: pd.DataFrame | None,
    risk_df: pd.DataFrame | None,
) -> None:
    """Render the full candidate profile view: header plus all six profile tabs."""
    dossier_row = get_candidate_row(dossiers_df, candidate_name)
    if dossier_row is None:
        st.error("This candidate could not be found in the current prototype data.")
        return

    readiness_row = get_readiness_row(readiness_df, candidate_name)
    context_rows = get_candidate_context_rows(risk_df, candidate_name)

    if st.button("← Back to search"):
        st.session_state.selected_candidate = None
        st.rerun()

    st.markdown(
        f"""
        <div class="sj-profile-header">
            <h2>{_safe_get(dossier_row, 'candidate_name')}</h2>
            <div class="sj-profile-sub">
                {_safe_get(dossier_row, 'court_name')} &middot; {_safe_get(dossier_row, 'court_type')}
                &middot; {_safe_get(dossier_row, 'incumbent_status')}
                &middot; {_party_badge_html(dossier_row.get('party', ''))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(
        [
            "Overview",
            "Professional Background",
            "Campaign Finance",
            "Court Context",
            "Public Record Notes",
            "Sources & Caveats",
        ]
    )
    with tabs[0]:
        render_overview_tab(dossier_row, readiness_row)
    with tabs[1]:
        render_professional_background_tab(dossier_row)
    with tabs[2]:
        render_campaign_finance_tab(dossier_row)
    with tabs[3]:
        render_court_context_tab(dossier_row)
    with tabs[4]:
        render_public_record_notes_tab(context_rows)
    with tabs[5]:
        render_sources_caveats_tab()


# ---------------------------------------------------------------------------
# Render: about the pipeline (technical reviewers only)
# ---------------------------------------------------------------------------

def render_about_pipeline() -> None:
    """Render the bottom 'About the data pipeline' expander for technical reviewers.

    This is the only place in the app where backend pipeline vocabulary
    (bronze/silver/validation/gold) is allowed to appear.
    """
    with st.expander("About the data pipeline"):
        st.markdown(
            "This prototype is built on top of a small internal data pipeline. "
            "In short: raw records are preserved, cleaned tables are generated, "
            "schema validation checks the data, and gold outputs power the "
            "candidate profiles shown above. Source caveats are preserved at "
            "every stage."
        )
        st.markdown(
            "**Bronze raw data → Silver cleaned data → Validation → "
            "Gold profile outputs → Candidate lookup**"
        )

        target_3_report = load_csv(TARGET_3_VALIDATION_PATH)
        gold_outputs_report = load_csv(GOLD_OUTPUTS_VALIDATION_PATH)

        if target_3_report is not None:
            st.markdown("**Candidate record validation**")
            st.dataframe(target_3_report, hide_index=True, width="stretch")
        else:
            st.caption(f"File not found: {TARGET_3_VALIDATION_PATH.relative_to(REPO_ROOT)}")

        if gold_outputs_report is not None:
            st.markdown("**Gold output validation**")
            st.dataframe(gold_outputs_report, hide_index=True, width="stretch")
        else:
            st.caption(f"File not found: {GOLD_OUTPUTS_VALIDATION_PATH.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the Spartan Judicial Candidate Lookup Streamlit app."""
    st.set_page_config(
        page_title="Spartan Judicial Candidate Lookup",
        page_icon="⚖️",
        layout="centered",
    )
    inject_custom_css()

    if "app_started" not in st.session_state:
        st.session_state.app_started = False
    if "selected_candidate" not in st.session_state:
        st.session_state.selected_candidate = None

    dossiers_df = load_csv(DOSSIERS_PATH)
    readiness_df = load_csv(READINESS_PATH)
    risk_df = load_csv(RISK_SIGNALS_PATH)

    if dossiers_df is None:
        st.error(f"Candidate data file not found: {DOSSIERS_PATH.relative_to(REPO_ROOT)}")
        return

    if not st.session_state.app_started:
        render_hero()
        return

    if st.session_state.selected_candidate:
        render_candidate_profile(st.session_state.selected_candidate, dossiers_df, readiness_df, risk_df)
    else:
        st.markdown('<div class="sj-section-label">Find a candidate</div>', unsafe_allow_html=True)
        st.markdown('<div class="sj-section-title">Search or browse the prototype</div>', unsafe_allow_html=True)

        search_tab, browse_tab = st.tabs(["Search by name", "Browse current clients"])
        with search_tab:
            render_search_interface(dossiers_df)
        with browse_tab:
            render_client_cards(dossiers_df)

    st.markdown('<hr class="sj-divider">', unsafe_allow_html=True)
    render_about_pipeline()


if __name__ == "__main__":
    main()
