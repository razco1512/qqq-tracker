"""
QQQ / TQQQ Strategy Dashboard — Phase 2
Adds Supabase persistence for ATH, manual targets, and alert flags.
Data fetching, chart rendering, and DB I/O are kept in separate layers.
"""

import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

import supabase_layer as db

# ─────────────────────────────────────────────
#  PAGE CONFIG  (must be the very first st call)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="QQQ / TQQQ Strategy Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] { font-size: 2rem; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; color: #9EA3AD; }
    [data-testid="stMetricDelta"] { font-size: 0.9rem; }
    .section-header {
        font-size: 1.05rem;
        font-weight: 600;
        color: #00D4FF;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    hr { border-color: #30363D; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
TICKER_QQQ   = "QQQ"
TICKER_TQQQ  = "TQQQ"
DRAWDOWN_PCT = 0.10

TIMEFRAME_OPTIONS = {
    "1 Month":  "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year":   "1y",
    "2 Years":  "2y",
    "5 Years":  "5y",
    "Max":      "max",
}

CHART_COLORS = {
    "qqq":    "#00D4FF",
    "tqqq":   "#FF6B35",
    "ath":    "#FFD700",
    "target": "#FF4B6E",
    "manual": "#39D353",
    "fill_qqq":  "rgba(0, 212, 255, 0.06)",
    "fill_tqqq": "rgba(255, 107, 53, 0.06)",
}

# ─────────────────────────────────────────────
#  YFINANCE LAYER
# ─────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(ticker: str, period: str) -> pd.DataFrame:
    """Return OHLCV DataFrame for *ticker* over *period* (5-min cache)."""
    t = yf.Ticker(ticker)
    df = t.history(period=period, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for {ticker} / period={period}")
    df.index = df.index.tz_localize(None)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_ath_yfinance(ticker: str) -> float:
    """Compute ATH from full yfinance history (fallback when DB has no value)."""
    t = yf.Ticker(ticker)
    df = t.history(period="max", auto_adjust=True)
    if df.empty:
        raise ValueError(f"No historical data for {ticker}")
    return float(df["Close"].max())


@st.cache_data(ttl=300, show_spinner=False)
def fetch_latest_price(ticker: str) -> float:
    """Return the most recent closing price for *ticker*."""
    t = yf.Ticker(ticker)
    df = t.history(period="5d", auto_adjust=True)
    if df.empty:
        raise ValueError(f"No recent data for {ticker}")
    return float(df["Close"].iloc[-1])


def compute_drawdown_target(ath: float, pct: float = DRAWDOWN_PCT) -> float:
    """Return ATH × (1 − pct)."""
    return ath * (1.0 - pct)


# ─────────────────────────────────────────────
#  CHART BUILDERS
# ─────────────────────────────────────────────

def _base_layout(title: str, y_range: list[float]) -> dict:
    """Shared Plotly dark layout. y_range = [min_padded, max_padded]."""
    return dict(
        title=dict(text=title, font=dict(size=16, color="#FAFAFA")),
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        font=dict(color="#9EA3AD", size=12),
        xaxis=dict(
            showgrid=True, gridcolor="#21262D", gridwidth=0.5,
            zeroline=False, showspikes=True,
            spikecolor="#444C56", spikethickness=1,
        ),
        yaxis=dict(
            title="Price (USD)",
            range=y_range,
            showgrid=True, gridcolor="#21262D", gridwidth=0.5,
            zeroline=False, showspikes=True,
            spikecolor="#444C56", spikethickness=1,
        ),
        hovermode="x unified",
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#30363D", borderwidth=1),
        margin=dict(l=20, r=20, t=50, b=20),
    )


def _y_range(df: pd.DataFrame) -> list[float]:
    """Return [min*0.98, max*1.02] for the period's Close prices."""
    lo = float(df["Close"].min())
    hi = float(df["Close"].max())
    return [lo * 0.98, hi * 1.02]


def build_qqq_chart(
    df: pd.DataFrame,
    ath: float,
    target: float,
    manual_target: float = 0.0,
) -> go.Figure:
    """QQQ area chart with ATH line, −10% target, and optional manual target."""
    fig = go.Figure()
    x_range = [df.index[0], df.index[-1]]

    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"],
        fill="tozeroy", fillcolor=CHART_COLORS["fill_qqq"],
        line=dict(color=CHART_COLORS["qqq"], width=2),
        name="QQQ Close",
        hovertemplate="<b>QQQ</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x_range, y=[ath, ath], mode="lines",
        line=dict(color=CHART_COLORS["ath"], width=1.5, dash="dash"),
        name=f"ATH  ${ath:,.2f}",
        hovertemplate=f"ATH: ${ath:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=x_range, y=[target, target], mode="lines",
        line=dict(color=CHART_COLORS["target"], width=1.5, dash="dash"),
        name=f"−10 % Target  ${target:,.2f}",
        hovertemplate=f"−10% target: ${target:,.2f}<extra></extra>",
    ))
    if manual_target > 0:
        fig.add_trace(go.Scatter(
            x=x_range, y=[manual_target, manual_target], mode="lines",
            line=dict(color=CHART_COLORS["manual"], width=1.5, dash="dot"),
            name=f"Manual Target  ${manual_target:,.2f}",
            hovertemplate=f"Manual target: ${manual_target:,.2f}<extra></extra>",
        ))

    fig.update_layout(**_base_layout("QQQ — Nasdaq 100 ETF", _y_range(df)))
    return fig


def build_tqqq_chart(df: pd.DataFrame, manual_target: float = 0.0) -> go.Figure:
    """TQQQ area chart with optional manual target line."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"],
        fill="tozeroy", fillcolor=CHART_COLORS["fill_tqqq"],
        line=dict(color=CHART_COLORS["tqqq"], width=2),
        name="TQQQ Close",
        hovertemplate="<b>TQQQ</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
    ))
    if manual_target > 0:
        x_range = [df.index[0], df.index[-1]]
        fig.add_trace(go.Scatter(
            x=x_range, y=[manual_target, manual_target], mode="lines",
            line=dict(color=CHART_COLORS["manual"], width=1.5, dash="dot"),
            name=f"Manual Target  ${manual_target:,.2f}",
            hovertemplate=f"Manual target: ${manual_target:,.2f}<extra></extra>",
        ))

    fig.update_layout(**_base_layout("TQQQ — 3× Leveraged Nasdaq 100 ETF", _y_range(df)))
    return fig


# ─────────────────────────────────────────────
#  SESSION STATE HELPERS
# ─────────────────────────────────────────────

def _init_session(state: dict) -> None:
    """
    Populate st.session_state from the DB state on the very first run.
    Subsequent reruns (caused by widget interactions) skip this so that
    user edits are not overwritten by a stale DB read.
    """
    if st.session_state.get("_db_initialized"):
        return
    st.session_state._db_initialized   = True
    st.session_state.qqq_manual        = state["manual_target_qqq"]
    st.session_state.tqqq_manual       = state["manual_target_tqqq"]
    st.session_state.qqq_alert         = state["alert_qqq_enabled"]
    st.session_state.tqqq_alert        = state["alert_tqqq_enabled"]
    # Shadow copy — used to detect writes needed
    st.session_state._last_saved = {
        "manual_target_qqq":  state["manual_target_qqq"],
        "manual_target_tqqq": state["manual_target_tqqq"],
        "alert_qqq_enabled":  state["alert_qqq_enabled"],
        "alert_tqqq_enabled": state["alert_tqqq_enabled"],
    }


def _maybe_persist(client) -> None:
    """
    Compare current widget values to the last-saved DB snapshot.
    If anything changed, upsert and update the shadow copy.
    """
    current = {
        "manual_target_qqq":  st.session_state.qqq_manual,
        "manual_target_tqqq": st.session_state.tqqq_manual,
        "alert_qqq_enabled":  st.session_state.qqq_alert,
        "alert_tqqq_enabled": st.session_state.tqqq_alert,
    }
    if current != st.session_state.get("_last_saved", {}):
        if db.save_state(client, **current):
            st.session_state._last_saved = current


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────

def render_sidebar() -> str:
    """Render controls; returns the selected yfinance period string.
    Widget values are read from / written to st.session_state directly.
    """
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        st.divider()

        # ── Timeframe ─────────────────────────
        st.markdown("#### Timeframe")
        label = st.radio(
            label="Select chart timeframe",
            options=list(TIMEFRAME_OPTIONS.keys()),
            index=0,
            label_visibility="collapsed",
        )

        st.divider()

        # ── Manual Targets + Alert flags ──────
        st.markdown("#### Manual Targets & Alerts")

        st.number_input(
            label="Manual QQQ Target ($)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="qqq_manual",
            help="Dotted green line on QQQ chart. Leave at 0 to hide.",
        )
        st.checkbox(
            label="Enable QQQ Alert",
            key="qqq_alert",
            help="Flag stored in DB — alert logic wired in Phase 3.",
        )

        st.markdown("")  # spacer

        st.number_input(
            label="Manual TQQQ Target ($)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="tqqq_manual",
            help="Dotted green line on TQQQ chart. Leave at 0 to hide.",
        )
        st.checkbox(
            label="Enable TQQQ Alert",
            key="tqqq_alert",
            help="Flag stored in DB — alert logic wired in Phase 3.",
        )

        st.divider()
        st.markdown(
            "<small style='color:#9EA3AD'>Data via Yahoo Finance · cached 5 min.<br>"
            "Settings auto-saved to Supabase.</small>",
            unsafe_allow_html=True,
        )

    return TIMEFRAME_OPTIONS[label]


# ─────────────────────────────────────────────
#  STRATEGY METRICS
# ─────────────────────────────────────────────

def render_strategy_metrics(ath: float, target: float, current_price: float) -> None:
    """Four-column metric row with live signal indicator."""
    drawdown_from_ath = (current_price - ath) / ath * 100
    gap_to_target_pct = (current_price - target) / target * 100
    triggered = current_price <= target

    st.markdown('<p class="section-header">Strategy Metrics — QQQ</p>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4, gap="medium")

    with col1:
        st.metric(
            label="All-Time High (ATH)",
            value=f"${ath:,.2f}",
            help="Highest adjusted closing price ever recorded for QQQ.",
        )
    with col2:
        st.metric(
            label="−10 % Buy Target",
            value=f"${target:,.2f}",
            help="ATH × 0.90 — strategy entry level for TQQQ.",
        )
    with col3:
        st.metric(
            label="Current QQQ Price",
            value=f"${current_price:,.2f}",
            delta=f"{drawdown_from_ath:+.2f}% from ATH",
            delta_color="inverse",
        )
    with col4:
        if triggered:
            st.metric(
                label="Signal",
                value="TRIGGERED",
                delta="Price ≤ −10 % target",
                delta_color="off",
            )
            st.error("🚨 Buy signal active — QQQ is at/below the −10 % target.", icon="🚨")
        else:
            st.metric(
                label="Gap to Target",
                value=f"{gap_to_target_pct:+.2f}%",
                delta="above target — no signal yet",
                delta_color="off",
            )


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main() -> None:
    # ── Header ────────────────────────────────
    st.markdown(
        "<h1 style='color:#00D4FF; margin-bottom:0;'>📈 QQQ / TQQQ Strategy Dashboard</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#9EA3AD; margin-top:0.25rem;'>"
        "Monitor the QQQ drawdown-from-ATH trigger for TQQQ entries · "
        "settings persisted to Supabase.</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Supabase: connect + load state ────────
    client     = db.get_supabase_client()
    db_state   = db.load_state(client)
    db_online  = client is not None

    # Seed session_state from DB on first load only
    _init_session(db_state)

    # ── Sidebar ───────────────────────────────
    period = render_sidebar()

    # Persist any sidebar changes that occurred this run
    _maybe_persist(client)

    # ── Market data ───────────────────────────
    with st.spinner("Fetching market data…"):
        try:
            current_price = fetch_latest_price(TICKER_QQQ)
            df_qqq        = fetch_history(TICKER_QQQ,  period)
            df_tqqq       = fetch_history(TICKER_TQQQ, period)
        except Exception as exc:
            st.error(f"Market data fetch failed: {exc}")
            st.stop()

    # ── ATH: prefer DB value, fall back to yfinance ──
    if db_state["ath_price"] is not None:
        ath = db_state["ath_price"]
    else:
        try:
            ath = fetch_ath_yfinance(TICKER_QQQ)
        except Exception as exc:
            st.error(f"ATH calculation failed: {exc}")
            st.stop()

    # Update DB if we have a new all-time high
    ath = db.update_ath_if_new_high(client, current_price, ath)
    target = compute_drawdown_target(ath)

    # ── DB status badge ───────────────────────
    if db_online:
        st.sidebar.success("Supabase connected", icon="🟢")
    else:
        st.sidebar.warning("Supabase offline — running on local data", icon="🟡")

    # ── Strategy metrics ──────────────────────
    render_strategy_metrics(ath, target, current_price)
    st.divider()

    # ── Charts ────────────────────────────────
    st.markdown('<p class="section-header">Price Charts</p>', unsafe_allow_html=True)

    qqq_chart  = build_qqq_chart(
        df_qqq, ath, target,
        manual_target=st.session_state.qqq_manual,
    )
    tqqq_chart = build_tqqq_chart(
        df_tqqq,
        manual_target=st.session_state.tqqq_manual,
    )

    st.plotly_chart(qqq_chart,  use_container_width=True, key="qqq_chart")
    st.plotly_chart(tqqq_chart, use_container_width=True, key="tqqq_chart")

    # ── Footer ────────────────────────────────
    st.divider()
    st.markdown(
        "<small style='color:#6E7681'>"
        "Phase 2 — Supabase persistence active. "
        "Email/push alerts coming in Phase 3.<br>"
        "Prices are delayed; not financial advice."
        "</small>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
