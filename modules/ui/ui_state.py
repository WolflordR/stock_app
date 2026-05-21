import os

import streamlit as st

from modules.backtest.strategy_config import DEFAULT_BUY_STRATEGIES, DEFAULT_SELL_STRATEGIES


def load_secret_env(var_name):
    if os.getenv(var_name):
        return
    try:
        secret_value = st.secrets.get(var_name)
    except Exception:
        secret_value = None
    if secret_value:
        os.environ[var_name] = str(secret_value)


def initialize_session_state():
    defaults = {
        "active_scan_job_id": None,
        "active_homepage_range_scan_job_id": None,
        "selected_view": "首頁",
        "backtest_mode": "歷史回測",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def ensure_strategy_state():
    st.session_state.setdefault("selected_buy_strategies", DEFAULT_BUY_STRATEGIES.copy())
    st.session_state.setdefault("selected_sell_strategies", DEFAULT_SELL_STRATEGIES.copy())
    st.session_state.setdefault("show_buy_strategy_dialog", False)
    st.session_state.setdefault("show_sell_strategy_dialog", False)


def seed_strategy_dialog_state(dialog_prefix, selected_values, metadata):
    for strategy_name in metadata:
        st.session_state[f"{dialog_prefix}_{strategy_name}"] = strategy_name in selected_values


def get_selected_from_dialog_state(dialog_prefix, metadata):
    return [
        strategy_name
        for strategy_name in metadata
        if st.session_state.get(f"{dialog_prefix}_{strategy_name}", False)
    ]
