"""
QQQ / TQQQ Strategy Dashboard — Phase 1
Data fetching + interactive UI (database & email alerts deferred to Phase 2).
"""

import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

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
#  CUSTOM CSS  – polish the dark theme a bit
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Metric card overrides */
    [data-testid="stMetricValue"] { font-size: 2rem; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; color: #9EA3AD; }
    [data-testid="stMetricDelta"] { font-size: 0.9rem; }

    /* Subtle card background for metric containers */
    .metric-card {
        background: #161B22;
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 1rem 1.25rem;
    }

    /* Section header */
    .section-header {
        font-size: 1.05rem;
        font-weight: 600;
        color: #00D4FF;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }

    /* Divider */
    hr { border-color: #30363D; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
TICKER_QQQ  = "QQQ"
TICKER_TQQQ = "TQQQ"
DRAWDOWN_PCT = 0.10          # 10 % drawdown trigger

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
    "qqq":      "#00D4FF",   # cyan
    "tqqq":     "#FF6B35",   # orange
    "ath":      "#FFD700",   # gold
    "target":   "#FF4B6E",   # rose-red
    "fill":     "rgba(0, 212, 255, 0.06)",
}

# ─────────────────────────────────────────────
#  DATA-FETCHING LAYER  (separated from UI)
# ─────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(ticker: str, period: str) -> pd.DataFrame:
    """Return OHLCV DataFrame for *ticker* over *period*.

    TTL = 5 min so the dashboard refreshes automatically without
    hammering Yahoo Finance on every widget interaction.
    """
    t = yf.Ticker(ticker)
    df = t.history(period=period, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for {ticker} / period={period}")
    df.index = df.index.tz_localize(None)   # drop tz for clean Plotly axis
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_ath(ticker: str) -> float:
    """Return the all-time-high closing price for *ticker*."""
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
#  CHART BUILDERS  (separated from data logic)
# ─────────────────────────────────────────────

def _base_layout(title: str, y_title: str = "Price (USD)") -> dict:
    """Shared Plotly layout settings."""
    return dict(
        title=dict(text=title, font=dict(size=16, color="#FAFAFA")),
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        font=dict(color="#9EA3AD", size=12),
        xaxis=dict(
            showgrid=True,
            gridcolor="#21262D",
            gridwidth=0.5,
            zeroline=False,
            showspikes=True,
            spikecolor="#444C56",
            spikethickness=1,
        ),
        yaxis=dict(
            title=y_title,
            showgrid=True,
            gridcolor="#21262D",
            gridwidth=0.5,
            zeroline=False,
            showspikes=True,
            spikecolor="#444C56",
            spikethickness=1,
        ),
        hovermode="x unified",
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor="#30363D",
            borderwidth=1,
        ),
        margin=dict(l=20, r=20, t=50, b=20),
    )


def build_qqq_chart(
    df: pd.DataFrame,
    ath: float,
    target: float,
) -> go.Figure:
    """Interactive QQQ line chart with ATH and −10 % reference lines."""
    fig = go.Figure()

    # Area fill below the line
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        fill="tozeroy",
        fillcolor=CHART_COLORS["fill"],
        line=dict(color=CHART_COLORS["qqq"], width=2),
        name="QQQ Close",
        hovertemplate="<b>QQQ</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
    ))

    x_range = [df.index[0], df.index[-1]]

    # ATH reference line
    fig.add_trace(go.Scatter(
        x=x_range,
        y=[ath, ath],
        mode="lines",
        line=dict(color=CHART_COLORS["ath"], width=1.5, dash="dash"),
        name=f"ATH  ${ath:,.2f}",
        hovertemplate=f"ATH: ${ath:,.2f}<extra></extra>",
    ))

    # −10 % target line
    fig.add_trace(go.Scatter(
        x=x_range,
        y=[target, target],
        mode="lines",
        line=dict(color=CHART_COLORS["target"], width=1.5, dash="dash"),
        name=f"−10 % Target  ${target:,.2f}",
        hovertemplate=f"−10% target: ${target:,.2f}<extra></extra>",
    ))

    fig.update_layout(**_base_layout("QQQ — Nasdaq 100 ETF"))
    return fig


def build_tqqq_chart(df: pd.DataFrame) -> go.Figure:
    """Interactive TQQQ line chart."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df["Close"],
        fill="tozeroy",
        fillcolor="rgba(255, 107, 53, 0.06)",
        line=dict(color=CHART_COLORS["tqqq"], width=2),
        name="TQQQ Close",
        hovertemplate="<b>TQQQ</b><br>%{x|%b %d, %Y}<br>$%{y:,.2f}<extra></extra>",
    ))

    fig.update_layout(**_base_layout("TQQQ — 3× Leveraged Nasdaq 100 ETF"))
    return fig


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────

def render_sidebar() -> str:
    """Render sidebar controls; return the selected yfinance period string."""
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        st.divider()

        st.markdown("#### Timeframe")
        label = st.radio(
            label="Select chart timeframe",
            options=list(TIMEFRAME_OPTIONS.keys()),
            index=3,              # default: 1 Year
            label_visibility="collapsed",
        )

        st.divider()
        st.markdown(
            "<small style='color:#9EA3AD'>Data via Yahoo Finance.<br>"
            "Cached for 5 minutes.</small>",
            unsafe_allow_html=True,
        )

    return TIMEFRAME_OPTIONS[label]


# ─────────────────────────────────────────────
#  STRATEGY METRICS SECTION
# ─────────────────────────────────────────────

def render_strategy_metrics(ath: float, target: float, current_price: float) -> None:
    """Display the key strategy numbers as metric cards."""
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
            help="ATH × 0.90 — the level at which the strategy triggers a TQQQ entry.",
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
                help="QQQ has reached or fallen below the −10% drawdown threshold.",
            )
            st.error("🚨 Buy signal active — QQQ is at/below the −10 % target.", icon="🚨")
        else:
            st.metric(
                label="Gap to Target",
                value=f"{gap_to_target_pct:+.2f}%",
                delta="above target — no signal yet",
                delta_color="off",
                help="How far QQQ is above the −10 % target. Negative = signal triggered.",
            )


# ─────────────────────────────────────────────
#  MAIN APP
# ─────────────────────────────────────────────

def main() -> None:
    # ── Header ────────────────────────────────
    st.markdown(
        "<h1 style='color:#00D4FF; margin-bottom:0;'>📈 QQQ / TQQQ Strategy Dashboard</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color:#9EA3AD; margin-top:0.25rem;'>"
        "Monitor the QQQ drawdown-from-ATH trigger for TQQQ entries.</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Sidebar (timeframe selector) ──────────
    period = render_sidebar()

    # ── Data fetching (all errors surface here) ──
    with st.spinner("Fetching market data…"):
        try:
            ath           = fetch_ath(TICKER_QQQ)
            target        = compute_drawdown_target(ath)
            current_price = fetch_latest_price(TICKER_QQQ)
            df_qqq        = fetch_history(TICKER_QQQ,  period)
            df_tqqq       = fetch_history(TICKER_TQQQ, period)
        except Exception as exc:
            st.error(f"Data fetch failed: {exc}")
            st.stop()

    # ── Strategy metrics ──────────────────────
    render_strategy_metrics(ath, target, current_price)
    st.divider()

    # ── Charts ────────────────────────────────
    st.markdown('<p class="section-header">Price Charts</p>', unsafe_allow_html=True)

    qqq_chart  = build_qqq_chart(df_qqq, ath, target)
    tqqq_chart = build_tqqq_chart(df_tqqq)

    st.plotly_chart(qqq_chart,  use_container_width=True, key="qqq_chart")
    st.plotly_chart(tqqq_chart, use_container_width=True, key="tqqq_chart")

    # ── Footer ────────────────────────────────
    st.divider()
    st.markdown(
        "<small style='color:#6E7681'>"
        "Phase 1 — Data & Charts only. "
        "Database persistence and email alerts coming in Phase 2.<br>"
        "Prices are delayed; not financial advice."
        "</small>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
