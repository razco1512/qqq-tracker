"""
supabase_layer.py — Phase 2
All Supabase I/O is isolated here so app.py stays clean and the layer
is easy to swap or mock in future phases.

Expected table: strategy_state (single row, id = 1)
  id                  integer PRIMARY KEY
  ath_price           double precision
  manual_target_qqq   double precision DEFAULT 0
  manual_target_tqqq  double precision DEFAULT 0
  alert_qqq_enabled   boolean DEFAULT false
  alert_tqqq_enabled  boolean DEFAULT false
  updated_at          timestamptz DEFAULT now()
"""

from __future__ import annotations

import streamlit as st

# ─────────────────────────────────────────────
#  Type alias (avoids hard import when Supabase
#  is not installed or secrets are absent)
# ─────────────────────────────────────────────
_CLIENT_TYPE = None  # set at runtime

STATE_ROW_ID = 1

# Default state used as fallback whenever the DB is empty or unreachable
DEFAULT_STATE: dict = {
    "id":                 STATE_ROW_ID,
    "ath_price":          None,
    "manual_target_qqq":  0.0,
    "manual_target_tqqq": 0.0,
    "alert_qqq_enabled":  False,
    "alert_tqqq_enabled": False,
}


# ─────────────────────────────────────────────
#  Client (cached for the lifetime of the app)
# ─────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_supabase_client():
    """
    Return an initialised Supabase client, or None if secrets are missing
    or the supabase package is not installed (graceful degradation).
    """
    try:
        from supabase import create_client  # type: ignore
        url: str = st.secrets["SUPABASE_URL"]
        key: str = st.secrets["SUPABASE_KEY"]
        if not url or not key or url.startswith("https://<"):
            return None
        return create_client(url, key)
    except Exception:
        return None


# ─────────────────────────────────────────────
#  Read
# ─────────────────────────────────────────────

def load_state(client) -> dict:
    """
    Fetch the strategy_state row from Supabase.
    Returns DEFAULT_STATE on any error (empty table, network failure, etc.).
    """
    if client is None:
        return dict(DEFAULT_STATE)
    try:
        resp = (
            client.table("strategy_state")
            .select("*")
            .eq("id", STATE_ROW_ID)
            .limit(1)
            .execute()
        )
        if resp.data:
            merged = dict(DEFAULT_STATE)
            merged.update(resp.data[0])
            # Normalise NULLs from DB to Python defaults
            merged["manual_target_qqq"]  = float(merged["manual_target_qqq"]  or 0.0)
            merged["manual_target_tqqq"] = float(merged["manual_target_tqqq"] or 0.0)
            merged["alert_qqq_enabled"]  = bool(merged["alert_qqq_enabled"])
            merged["alert_tqqq_enabled"] = bool(merged["alert_tqqq_enabled"])
            merged["ath_price"] = (
                float(merged["ath_price"]) if merged["ath_price"] else None
            )
            return merged
        # Table exists but row is absent — seed it silently
        _seed_row(client)
        return dict(DEFAULT_STATE)
    except Exception:
        return dict(DEFAULT_STATE)


# ─────────────────────────────────────────────
#  Write helpers
# ─────────────────────────────────────────────

def save_state(client, **fields) -> bool:
    """
    Upsert arbitrary fields into the strategy_state row.
    Returns True on success, False on failure.
    """
    if client is None:
        return False
    try:
        payload = {"id": STATE_ROW_ID, **fields}
        client.table("strategy_state").upsert(payload).execute()
        return True
    except Exception:
        return False


def update_ath_if_new_high(client, current_price: float, stored_ath: float | None) -> float:
    """
    If *current_price* exceeds *stored_ath* (or ath is unknown), persist the
    new ATH to the DB and return it. Otherwise return *stored_ath* unchanged.
    """
    if stored_ath is None or current_price > stored_ath:
        save_state(client, ath_price=current_price)
        return current_price
    return stored_ath


# ─────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────

def _seed_row(client) -> None:
    """Insert the default row if it doesn't exist yet."""
    try:
        client.table("strategy_state").upsert(DEFAULT_STATE).execute()
    except Exception:
        pass
