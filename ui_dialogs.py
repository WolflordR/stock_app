import streamlit as st

from strategy_config import BUY_STRATEGY_METADATA, SELL_STRATEGY_METADATA
from ui_state import get_selected_from_dialog_state


@st.dialog("選擇買入策略", width="large")
def render_buy_strategy_dialog():
    st.caption("勾選你要同時成立的買點條件。所有已選條件都成立時，系統才會買入。")
    for strategy_name, meta in BUY_STRATEGY_METADATA.items():
        st.checkbox(
            f"{meta['title']}｜{meta['summary']}",
            key=f"buy_strategy_dialog_{strategy_name}",
        )
        st.caption(meta["description"])

    save_col, cancel_col = st.columns(2)
    if save_col.button("儲存買入策略", use_container_width=True):
        st.session_state["selected_buy_strategies"] = get_selected_from_dialog_state(
            "buy_strategy_dialog",
            BUY_STRATEGY_METADATA,
        )
        st.session_state["show_buy_strategy_dialog"] = False
        st.rerun()
    if cancel_col.button("取消", use_container_width=True):
        st.session_state["show_buy_strategy_dialog"] = False
        st.rerun()


@st.dialog("選擇賣出策略", width="large")
def render_sell_strategy_dialog():
    st.caption("勾選任何一個出場條件都會賣出。你可以混搭固定停損、結構停損與移動停損。")
    for strategy_name, meta in SELL_STRATEGY_METADATA.items():
        st.checkbox(
            f"{meta['title']}｜{meta['summary']}",
            key=f"sell_strategy_dialog_{strategy_name}",
        )
        st.caption(meta["description"])

    save_col, cancel_col = st.columns(2)
    if save_col.button("儲存賣出策略", use_container_width=True):
        st.session_state["selected_sell_strategies"] = get_selected_from_dialog_state(
            "sell_strategy_dialog",
            SELL_STRATEGY_METADATA,
        )
        st.session_state["show_sell_strategy_dialog"] = False
        st.rerun()
    if cancel_col.button("取消", use_container_width=True):
        st.session_state["show_sell_strategy_dialog"] = False
        st.rerun()
